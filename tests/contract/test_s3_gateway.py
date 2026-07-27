"""Contract tests for the S3 gateway.

Uses a mock boto3 client — no real network calls are made. Verifies that
``upload_bytes``, ``upload_file``, and ``presign_get`` call the SDK with
the correct arguments, and that SDK exceptions are normalized to
``ProviderError`` with the right retryability semantics.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.s3.client import S3Gateway


def _make_client_error(
    code: str = "InternalError",
    message: str = "something went wrong",
    status: int | None = 500,
    request_id: str = "req-err-001",
) -> ClientError:
    response: dict[str, object] = {
        "Error": {"Code": code, "Message": message},
        "ResponseMetadata": {"RequestId": request_id},
    }
    if status is not None:
        response["ResponseMetadata"]["HTTPStatusCode"] = status  # type: ignore[union-attr]
    return ClientError(response, "PutObject")  # type: ignore[arg-type]


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.put_object.return_value = {
        "ResponseMetadata": {"RequestId": "req-test-123"},
    }
    client.upload_file.return_value = None
    client.generate_presigned_url.return_value = "https://s3.example.com/presigned-get-url"
    client.close = MagicMock()
    return client


@pytest.fixture
def gateway(mock_client: MagicMock) -> S3Gateway:
    return S3Gateway(
        client=mock_client,
        bucket="test-bucket",
        presign_ttl=3600,
    )


class TestS3GatewayUpload:
    async def test_upload_bytes_calls_put_object(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        await gateway.upload_bytes(key="video/test/abc", data=b"video-bytes", mime_type="video/mp4")

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="video/test/abc",
            Body=b"video-bytes",
            ContentType="video/mp4",
        )

    async def test_upload_file_calls_upload_file(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        await gateway.upload_file(
            key="video/test/xyz", file_path="/tmp/video.mp4", mime_type="video/mp4"
        )

        mock_client.upload_file.assert_called_once_with(
            Filename="/tmp/video.mp4",
            Bucket="test-bucket",
            Key="video/test/xyz",
            ExtraArgs={"ContentType": "video/mp4"},
        )

    async def test_presign_get_returns_url(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        url = await gateway.presign_get(key="video/test/abc")

        assert url == "https://s3.example.com/presigned-get-url"
        mock_client.generate_presigned_url.assert_called_once()

    async def test_presign_get_uses_custom_ttl(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        await gateway.presign_get(key="k", expires=7200)

        call_args = mock_client.generate_presigned_url.call_args
        assert call_args.kwargs["ExpiresIn"] == 7200


class TestS3GatewayErrorNormalization:
    async def test_server_error_5xx_is_retryable(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_client_error(status=500)

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status == 500

    async def test_server_error_4xx_is_not_retryable(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_client_error(
            status=403, code="AccessDenied", message="denied"
        )

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is False
        assert exc_info.value.http_status == 403

    async def test_server_error_429_is_retryable(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_client_error(
            status=429, code="SlowDown", message="slow down"
        )

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status == 429

    async def test_connection_error_no_http_status_is_retryable(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = _make_client_error(status=None)

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.http_status is None

    async def test_unknown_error_is_retryable(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.put_object.side_effect = RuntimeError("unexpected")

        with pytest.raises(ProviderError) as exc_info:
            await gateway.upload_bytes(key="k", data=b"d", mime_type="video/mp4")

        assert exc_info.value.retryable is True
        assert exc_info.value.code == "S3_UNKNOWN_ERROR"

    async def test_error_in_presign_is_normalized(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        mock_client.generate_presigned_url.side_effect = _make_client_error(status=500)

        with pytest.raises(ProviderError) as exc_info:
            await gateway.presign_get(key="k")

        assert exc_info.value.operation == "presign"


class TestS3GatewayClose:
    async def test_close_calls_client_close(
        self, gateway: S3Gateway, mock_client: MagicMock
    ) -> None:
        await gateway.close()
        mock_client.close.assert_called_once()

    async def test_close_is_idempotent(self, gateway: S3Gateway, mock_client: MagicMock) -> None:
        await gateway.close()
        await gateway.close()
        mock_client.close.assert_called_once()
