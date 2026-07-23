"""SSRF-resistant downloader for trusted provider media URLs.

Every hop is resolved and validated before connecting. The request connects to
the validated IP address while preserving the original HTTP Host header and TLS
SNI hostname, preventing DNS rebinding between validation and connection.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from urllib.parse import urljoin, urlunsplit

import httpx
from pydantic import BaseModel

from modelark_mcp.security.url_policy import AddressResolver, ValidatedUrl, validate_url

HostPolicy = Callable[[str], bool]


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
            validated = validate_url(current_url, resolver=self._resolver)
            if not trusted_hosts(validated.hostname):
                raise ValueError(
                    f"Refusing to download from untrusted host '{validated.hostname}'."
                )

            response = await self._request_pinned(validated, max_bytes=max_bytes)
            if not response.is_redirect:
                response.raise_for_status()
                return DownloadedMedia(
                    body=response.content,
                    content_type=_content_type(response),
                    final_url=current_url,
                )

            location = response.headers.get("location")
            if not location:
                raise ValueError(
                    f"Redirect response from '{current_url}' is missing a Location header."
                )
            if redirect_count == max_redirects:
                raise ValueError(f"Too many redirects from '{url}'.")
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
                await response.aread()
                return response

            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError:
                    declared_bytes = 0
                if declared_bytes > max_bytes:
                    raise ValueError(
                        f"Download Content-Length ({declared_bytes} bytes) exceeds "
                        f"limit ({max_bytes} bytes)."
                    )

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError(f"Downloaded media exceeds limit ({max_bytes} bytes).")
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
