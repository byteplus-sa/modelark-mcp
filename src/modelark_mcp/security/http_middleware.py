"""ASGI request-size policy and rate limiting for Streamable HTTP."""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject declared and streamed HTTP request bodies above a hard limit."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await PlainTextResponse("Invalid Content-Length", status_code=400)(
                    scope, receive, send
                )
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Request body too large", status_code=413)
        await response(scope, receive, send)


class RateLimitMiddleware:
    """Per-client-IP token bucket rate limiter for HTTP requests."""

    _MAX_BUCKETS = 10_000

    def __init__(
        self,
        app: ASGIApp,
        *,
        rpm: int,
        burst: int | None = None,
        trust_proxy_headers: bool = False,
    ) -> None:
        self.app = app
        self.rpm = rpm
        self.capacity = burst if burst and burst > 0 else rpm
        self._rate = rpm / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.rpm <= 0:
            await self.app(scope, receive, send)
            return

        ip = self._client_key(scope)

        retry_after = await self._consume(ip)
        if retry_after > 0:
            response = PlainTextResponse(
                "Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(math.ceil(retry_after))},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _client_key(self, scope: Scope) -> str:
        if self.trust_proxy_headers:
            headers = dict(scope.get("headers", []))
            forwarded = headers.get(b"x-forwarded-for")
            if isinstance(forwarded, bytes):
                first = forwarded.decode("latin-1").split(",", 1)[0].strip()
                if first:
                    return first
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    async def _consume(self, ip: str) -> float:
        """Try to consume one token. Return 0 on success, or seconds to wait."""
        now = time.monotonic()
        async with self._lock:
            if len(self._buckets) > self._MAX_BUCKETS:
                self._evict_expired()
            tokens, last_refill = self._buckets.get(ip, (self.capacity, now))
            elapsed = now - last_refill
            tokens = min(self.capacity, tokens + elapsed * self._rate)
            self._buckets[ip] = (tokens, now)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[ip] = (tokens, now)
                return 0.0
            deficit = 1.0 - tokens
            return deficit / self._rate if self._rate > 0 else 0.0

    def _evict_expired(self) -> None:
        """Remove buckets whose tokens have fully refilled (no active throttle)."""
        now = time.monotonic()
        expired = [
            ip
            for ip, (tokens, last_refill) in self._buckets.items()
            if tokens >= self.capacity or (now - last_refill) * self._rate >= self.capacity - tokens
        ]
        for ip in expired:
            del self._buckets[ip]
