"""Seed Speech HTTP gateway — client for Seed Audio (full-scene audio generation).

Seed Audio is hosted by Seed Speech and uses ``X-Api-Key`` authentication,
distinct from ModelArk's ``Authorization: Bearer``. The gateway handles
request/response, error normalization, and diagnostic ``X-Tt-Logid`` capture.
"""

from __future__ import annotations

from typing import Any

import httpx

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error
from modelark_mcp.observability.logger import info as log_info


class SeedSpeechGateway:
    """Authenticated HTTP client for Seed Speech API calls."""

    PROVIDER: ProviderName = "seed-speech"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.seed_audio_api_key
        self._base_url = (base_url or settings.seed_audio_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout),
                follow_redirects=False,
            )
        return self._client

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self, request_id: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Api-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request_id:
            headers["X-Api-Request-Id"] = request_id
        return headers

    async def post(
        self,
        path: str,
        json_body: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> httpx.Response:
        """POST to Seed Speech and return the raw response."""
        client = await self._ensure_client()
        url = f"{self._base_url}{path}"
        log_info("seed_speech_request", method="POST", path=path)
        return await client.post(url, json=json_body, headers=self._headers(request_id))

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def extract_log_id(response: httpx.Response) -> str | None:
        """Extract the diagnostic ``X-Tt-Logid`` from response headers."""
        value = response.headers.get("X-Tt-Logid") or response.headers.get("x-tt-logid")
        return str(value) if value is not None else None

    @staticmethod
    def normalize_error(
        response: httpx.Response,
        operation: str,
    ) -> ProviderError:
        """Normalize an error HTTP response into a ``ProviderError``."""
        log_id = SeedSpeechGateway.extract_log_id(response)
        status = response.status_code

        try:
            body = response.json()
        except Exception:
            body = {"message": response.text}

        code = str(body.get("code", "")) if isinstance(body, dict) else ""
        message = body.get("message", str(body)) if isinstance(body, dict) else str(body)

        # Seed Audio has no published error taxonomy. Treat 5xx as retryable.
        retryable = status >= 500

        normalized = NormalizedProviderError(
            provider="seed-speech",
            operation=operation,
            http_status=status,
            code=code or None,
            message=message,
            request_id=log_id,
            retryable=retryable,
        )
        log_error(
            "seed_speech_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            log_id=log_id,
        )
        return ProviderError(normalized)

    @staticmethod
    def normalize_timeout(operation: str) -> ProviderError:
        """Normalize a timeout — Seed Audio mutations are not safely retryable."""
        return ProviderError(
            NormalizedProviderError(
                provider="seed-speech",
                operation=operation,
                http_status=None,
                code="TIMEOUT",
                message=(
                    f"Request timed out during '{operation}'. "
                    "The audio generation may have succeeded. "
                    "Do not retry; reconcile using the X-Api-Request-Id."
                ),
                request_id=None,
                retryable=False,
                ambiguous_completion=True,
            )
        )

    @staticmethod
    def normalize_connection_error(operation: str, exc: Exception) -> ProviderError:
        """Normalize a connection error."""
        return ProviderError(
            NormalizedProviderError(
                provider="seed-speech",
                operation=operation,
                http_status=None,
                code="CONNECTION_ERROR",
                message=f"Failed to connect to Seed Speech: {exc}",
                request_id=None,
                retryable=True,
            )
        )
