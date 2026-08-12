"""Unit tests for the IP-pinned safe media downloader."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from modelark_mcp.security.safe_downloader import SafeDownloader, SafeDownloadError


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
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/start?token=must-not-leak",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()
    assert exc_info.value.code == "redirect_rejected"
    assert exc_info.value.retryable is False
    assert "token=" not in str(exc_info.value)


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
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()
    assert called is False
    assert exc_info.value.code == "invalid_url"
    assert exc_info.value.retryable is False


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
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()
    assert exc_info.value.code == "too_large"
    assert exc_info.value.retryable is False


async def test_chunked_oversized_body_is_rejected() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream(b"1234", b"5678"))

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=6,
            )
    finally:
        await downloader.close()
    assert exc_info.value.code == "too_large"


async def test_redirect_limit_is_enforced() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/start",
                trusted_hosts=trusted_host,
                max_bytes=1024,
                max_redirects=1,
            )
    finally:
        await downloader.close()
    assert exc_info.value.code == "redirect_rejected"


async def test_untrusted_initial_host_does_not_leak_query() -> None:
    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
    )
    try:
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://untrusted.example/output.mp4?signature=secret",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()

    assert exc_info.value.code == "untrusted_host"
    assert exc_info.value.retryable is False
    assert "untrusted.example" not in str(exc_info.value)
    assert "signature=" not in str(exc_info.value)


async def test_timeout_is_typed_and_retryable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out at signed URL", request=request)

    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/output?signature=secret",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()

    assert exc_info.value.code == "network_error"
    assert exc_info.value.retryable is True
    assert "signature=" not in str(exc_info.value)


@pytest.mark.parametrize("status_code", [404, 410])
async def test_expired_source_is_classified(status_code: int) -> None:
    downloader = SafeDownloader(
        resolver=public_resolver,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status_code, content=b"gone")
        ),
    )
    try:
        with pytest.raises(SafeDownloadError) as exc_info:
            await downloader.download(
                "https://media.byteplus.com/output",
                trusted_hosts=trusted_host,
                max_bytes=1024,
            )
    finally:
        await downloader.close()

    assert exc_info.value.code == "source_expired"
    assert exc_info.value.retryable is False


async def test_redirect_body_is_not_buffered() -> None:
    class FailIfReadStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            raise AssertionError("redirect body must not be read")
            yield b""  # pragma: no cover

        async def aclose(self) -> None:
            return None

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"location": "/final"},
                stream=FailIfReadStream(),
            )
        return httpx.Response(200, content=b"done")

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

    assert result.body == b"done"
