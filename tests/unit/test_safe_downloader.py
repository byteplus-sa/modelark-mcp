"""Unit tests for the IP-pinned safe media downloader."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from modelark_mcp.security.safe_downloader import SafeDownloader
from modelark_mcp.security.url_policy import UrlValidationError


def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def trusted_host(hostname: str) -> bool:
    return hostname == "media.byteplus.com"


class ChunkStream(httpx.AsyncByteStream):
    """Async response stream without a Content-Length header."""

    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


async def test_download_connects_to_validated_ip_with_host_and_sni() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers["host"]
        observed["sni"] = request.extensions["sni_hostname"]
        return httpx.Response(
            200,
            content=b"image-bytes",
            headers={"content-type": "image/png; charset=binary"},
        )

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await downloader.download(
            "https://media.byteplus.com/output/image.png?token=test",
            trusted_hosts=trusted_host,
            max_bytes=1024,
        )
    finally:
        await downloader.close()

    assert observed == {
        "url": "https://93.184.216.34/output/image.png?token=test",
        "host": "media.byteplus.com",
        "sni": "media.byteplus.com",
    }
    assert result.body == b"image-bytes"
    assert result.content_type == "image/png"
    assert result.final_url == "https://media.byteplus.com/output/image.png?token=test"


async def test_relative_redirect_is_revalidated_and_followed() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, content=b"done", headers={"content-type": "video/mp4"})

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await downloader.download(
            "https://media.byteplus.com/start",
            trusted_hosts=trusted_host,
            max_bytes=1024,
        )
    finally:
        await downloader.close()

    assert requests == ["https://93.184.216.34/start", "https://93.184.216.34/final"]
    assert result.final_url == "https://media.byteplus.com/final"


async def test_untrusted_redirect_is_rejected() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://attacker.example/final"})

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="untrusted host"):
            await downloader.download(
                "https://media.byteplus.com/start",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()


async def test_private_dns_result_is_rejected_before_request() -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"unsafe")

    downloader = SafeDownloader(
        resolver=lambda _host, _port: ("10.0.0.1",),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()
    assert called is False


async def test_declared_oversized_body_is_rejected() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"small",
            headers={"content-length": "2048"},
        )

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="Content-Length"):
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()


async def test_chunked_oversized_body_is_rejected() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream(b"1234", b"5678"))

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="exceeds limit"):
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=6,
            )
    finally:
        await downloader.close()


async def test_redirect_limit_is_enforced() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="Too many redirects"):
            await downloader.download(
                "https://media.byteplus.com/start",
                trusted_hosts=trusted_host,
                max_bytes=1024,
                max_redirects=1,
            )
    finally:
        await downloader.close()
