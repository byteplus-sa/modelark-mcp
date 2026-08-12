"""SSRF-resistant downloader for trusted provider media URLs.

Every hop is resolved and validated before connecting. The request connects to
the validated IP address while preserving the original HTTP Host header and TLS
SNI hostname, preventing DNS rebinding between validation and connection.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from typing import Literal
from urllib.parse import urljoin, urlunsplit

import httpx
from pydantic import BaseModel

from modelark_mcp.security.url_policy import AddressResolver, ValidatedUrl, validate_url

HostPolicy = Callable[[str], bool]
SafeDownloadErrorCode = Literal[
    "untrusted_host",
    "too_large",
    "invalid_url",
    "redirect_rejected",
    "source_expired",
    "http_error",
    "network_error",
]


class SafeDownloadError(ValueError):
    """Classified download failure with a URL-safe client message."""

    def __init__(
        self,
        code: SafeDownloadErrorCode,
        safe_message: str,
        *,
        retryable: bool,
    ) -> None:
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        super().__init__(safe_message)


class DownloadedMedia(BaseModel):
    """Downloaded media returned after all safety checks pass."""

    body: bytes
    content_type: str | None
    final_url: str


class SafeDownloader:
    """Download HTTPS media through an IP-pinned, redirect-safe client."""

    def __init__(
        self,
        *,
        timeout: float = 120.0,
        connect_timeout: float = 30.0,
        resolver: AddressResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._resolver = resolver
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def download(
        self,
        url: str,
        *,
        trusted_hosts: HostPolicy,
        max_bytes: int,
        max_redirects: int = 5,
    ) -> DownloadedMedia:
        """Download a trusted URL while revalidating and pinning every hop."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must not be negative")

        current_url = url
        for redirect_count in range(max_redirects + 1):
            try:
                validated = validate_url(current_url, resolver=self._resolver)
            except Exception as exc:
                code: SafeDownloadErrorCode = (
                    "invalid_url" if redirect_count == 0 else "redirect_rejected"
                )
                message = (
                    "Provider output URL failed safety validation."
                    if redirect_count == 0
                    else "Provider output redirect failed safety validation."
                )
                raise SafeDownloadError(code, message, retryable=False) from exc
            if not trusted_hosts(validated.hostname):
                code = "untrusted_host" if redirect_count == 0 else "redirect_rejected"
                message = (
                    "Provider output host is not trusted."
                    if redirect_count == 0
                    else "Provider output redirected to an untrusted host."
                )
                raise SafeDownloadError(code, message, retryable=False)

            try:
                response = await self._request_pinned(validated, max_bytes=max_bytes)
            except SafeDownloadError:
                raise
            except httpx.TimeoutException as exc:
                raise SafeDownloadError(
                    "network_error",
                    "Provider output download timed out.",
                    retryable=True,
                ) from exc
            except httpx.TransportError as exc:
                raise SafeDownloadError(
                    "network_error",
                    "Provider output download failed due to a network error.",
                    retryable=True,
                ) from exc
            if not response.is_redirect:
                if response.status_code in {404, 410}:
                    raise SafeDownloadError(
                        "source_expired",
                        "Provider output is no longer available.",
                        retryable=False,
                    )
                if response.is_error:
                    retryable = response.status_code in {408, 429} or response.status_code >= 500
                    raise SafeDownloadError(
                        "http_error",
                        f"Provider output download returned HTTP {response.status_code}.",
                        retryable=retryable,
                    )
                return DownloadedMedia(
                    body=response.content,
                    content_type=_content_type(response),
                    final_url=current_url,
                )

            location = response.headers.get("location")
            if not location:
                raise SafeDownloadError(
                    "redirect_rejected",
                    "Provider output redirect is missing a destination.",
                    retryable=False,
                )
            if redirect_count == max_redirects:
                raise SafeDownloadError(
                    "redirect_rejected",
                    "Provider output exceeded the redirect limit.",
                    retryable=False,
                )
            current_url = urljoin(current_url, location)

        raise AssertionError("redirect loop must return or raise")

    async def _request_pinned(
        self,
        validated: ValidatedUrl,
        *,
        max_bytes: int,
    ) -> httpx.Response:
        """Connect to a validated IP while preserving Host and TLS SNI."""
        address = validated.addresses[0]
        connect_url = _connect_url(validated, address)
        headers = {"Host": _host_header(validated)}
        extensions = {"sni_hostname": validated.hostname}

        async with self._client.stream(
            "GET",
            connect_url,
            headers=headers,
            extensions=extensions,
        ) as response:
            if response.is_redirect:
                # A redirect body is irrelevant and may itself be oversized. Return
                # only the metadata needed by the hop-by-hop redirect policy.
                return httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    request=response.request,
                    extensions=response.extensions,
                )

            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError:
                    declared_bytes = 0
                if declared_bytes > max_bytes:
                    raise SafeDownloadError(
                        "too_large",
                        f"Provider output exceeds the {max_bytes}-byte artifact limit.",
                        retryable=False,
                    )

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise SafeDownloadError(
                        "too_large",
                        f"Provider output exceeds the {max_bytes}-byte artifact limit.",
                        retryable=False,
                    )
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
                extensions=response.extensions,
            )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()


def _connect_url(
    validated: ValidatedUrl,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> str:
    host = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    default_port = 443 if validated.parsed.scheme == "https" else 80
    netloc = host if validated.port == default_port else f"{host}:{validated.port}"
    return urlunsplit(
        (
            validated.parsed.scheme,
            netloc,
            validated.parsed.path or "/",
            validated.parsed.query,
            "",
        )
    )


def _host_header(validated: ValidatedUrl) -> str:
    default_port = 443 if validated.parsed.scheme == "https" else 80
    return (
        validated.hostname
        if validated.port == default_port
        else f"{validated.hostname}:{validated.port}"
    )


def _content_type(response: httpx.Response) -> str | None:
    value: str | None = response.headers.get("content-type")
    if not value:
        return None
    return value.split(";", maxsplit=1)[0].strip().lower()
