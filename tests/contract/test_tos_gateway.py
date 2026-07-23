"""Contract tests for the TOS gateway.

Uses a mock SDK client — no real network calls are made.  Verifies that
``upload_bytes``, ``upload_file``, and ``presign_get`` call the SDK with
the correct arguments, and that SDK exceptions are normalized to
``ProviderError`` with the right retryability semantics.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from tos.exceptions import TosClientError, TosServerError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.tos.client import TosGateway


class _FakeOutput:
    def __init__(self, request_id: str = "req-test-123") -> None:
        self.request_id = request_id


def _make_server_error(status_code: int, code: str, message: str) -> TosServerError:
    resp = MagicMock()
    resp.status = status_code
    resp.status_code = status_code
    resp.request_id = "req-err-001"
    exc = TosServerError(resp, message, code, "host-id", "/bucket/key")
    return exc


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.put_object.return_value = _FakeOutput()
    client.put_object_from_file.return_value = _FakeOutput()
    client.pre_signed_url.return_value = "https://tos.example.com/presigned-get-url"
    client.close = MagicMock()
    return client


@pytest.fixture
def gateway(mock_client: MagicMock) -> TosGateway:
    from modelark_mcp.config.env import get_settings

    get_settings.cache_clear()
    return TosGateway(
        client=mock_client,
        bucket="test-bucket",
        presign_ttl=3600,
    )


class TestTosGatewayUpload:
    async def test_upload_bytes_calls_put_object(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        await gateway.upload_bytes(key="video/test/abc", data=b"video-bytes", mime_type="video/mp4")

        mock_client.put_object.assert_called_once_with(
            bucket="test-bucket",
            key="video/test/abc",
            content=b"video-bytes",
            content_type="video/mp4",
        )

    async def test_upload_file_calls_put_object_from_file(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        await gateway.upload_file(
            key="video/test/xyz", file_path="/tmp/video.mp4", mime_type="video/mp4"
        )

        mock_client.put_object_from_file.assert_called_once_with(
            bucket="test-bucket",
            key="video/test/xyz",
            file_path="/tmp/video.mp4",
            content_type="video/mp4",
        )

    async def test_presign_get_returns_url(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        url = await gateway.presign_get(key="video/test/abc")

        assert url == "https://tos.example.com/presigned-get-url"
        mock_client.pre_signed_url.assert_called_once()

    async def test_presign_get_uses_custom_ttl(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        await gateway.presign_get(key="k", expires=7200)

        call_args = mock_client.pre_signed_url.call_args
        assert call_args.kwargs["expires"] == 7200


class TestTosGatewayErrorNormalization:
    async def test_server_error_5xx_is_retryable(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_server_error(500, "INTERNAL", "boom")

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status == 500
        assert exc_info.value.code == "INTERNAL"

    async def test_server_error_4xx_is_not_retryable(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_server_error(403, "FORBIDDEN", "denied")

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is False
        assert exc_info.value.http_status == 403

    async def test_server_error_429_is_retryable(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_server_error(
            429, "TOO_MANY_REQUESTS", "slow down"
        )

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status == 429

    async def test_client_error_is_retryable(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = TosClientError("conn reset", Exception("cause"))

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.code == "TOS_CLIENT_ERROR"

    async def test_unknown_error_is_retryable(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = RuntimeError("unexpected")

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.code == "TOS_UNKNOWN_ERROR"

    async def test_error_in_presign_is_normalized(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        mock_client.pre_signed_url.side_effect = TosClientError(
            "signing failed", Exception("cause")
        )

        with pytest.raises(ProviderError) as exc_info:
            await gateway.presign_get(key="k")

        assert exc_info.value.operation == "presign"


class TestTosGatewayClose:
    async def test_close_calls_client_close(
        self, gateway: TosGateway, mock_client: MagicMock
    ) -> None:
        await gateway.close()
        mock_client.close.assert_called_once()

    async def test_close_is_idempotent(self, gateway: TosGateway, mock_client: MagicMock) -> None:
        await gateway.close()
        await gateway.close()
        mock_client.close.assert_called_once()
