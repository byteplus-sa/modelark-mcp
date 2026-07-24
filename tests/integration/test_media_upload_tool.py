"""Integration tests for the ``media_upload`` tool.

Uses the shared ``test_env`` / ``fake_ctx`` fixtures so the runtime
(budget ledger, provider limiters) is real.  The ``TosGateway`` is mocked
via ``patch`` so no SDK client or network is involved.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.tools.media_upload import (
    MediaUploadInput,
    MediaUploadOutput,
    media_upload,
)
from tests.fixtures.fake_context import FakeContext


def _mock_gateway() -> AsyncMock:
    gw = AsyncMock()
    gw.upload_bytes = AsyncMock(return_value=None)
    gw.upload_file = AsyncMock(return_value=None)
    gw.presign_get = AsyncMock(return_value="https://tos.example.com/presigned-url")
    gw.close = AsyncMock()
    return gw


class TestMediaUploadBase64:
    async def test_base64_upload_success(self, test_env: None, fake_ctx: FakeContext) -> None:
        data = base64.b64encode(b"fake-video-bytes").decode()
        mock_gw = _mock_gateway()

        with patch("modelark_mcp.tools.media_upload.TosGateway", return_value=mock_gw):
            result = await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    data=data,
                ),
                fake_ctx,
            )

        assert isinstance(result, MediaUploadOutput)
        assert result.url == "https://tos.example.com/presigned-url"
        assert result.bytes == len(b"fake-video-bytes")
        assert "references/video/" in result.object_key
        mock_gw.upload_bytes.assert_called_once()
        mock_gw.presign_get.assert_called_once()
        mock_gw.close.assert_called_once()

    async def test_base64_upload_with_custom_prefix(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        data = base64.b64encode(b"img").decode()
        mock_gw = _mock_gateway()

        with patch("modelark_mcp.tools.media_upload.TosGateway", return_value=mock_gw):
            result = await media_upload(
                MediaUploadInput(
                    media_type="image",
                    mime_type="image/png",
                    data=data,
                    key_prefix="uploads/2026",
                ),
                fake_ctx,
            )

        assert "uploads/2026/image/" in result.object_key


class TestMediaUploadFilePath:
    async def test_file_path_upload_success(
        self, test_env: None, fake_ctx: FakeContext, tmp_path: object
    ) -> None:
        from pathlib import Path

        video_file = Path(str(tmp_path)) / "clip.mp4"
        video_file.write_bytes(b"fake-video-content")

        mock_gw = _mock_gateway()

        with patch("modelark_mcp.tools.media_upload.TosGateway", return_value=mock_gw):
            result = await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    file_path=str(video_file),
                ),
                fake_ctx,
            )

        assert isinstance(result, MediaUploadOutput)
        assert result.bytes == len(b"fake-video-content")
        mock_gw.upload_file.assert_called_once()
        mock_gw.upload_bytes.assert_not_called()

    async def test_file_path_nonexistent_raises(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        with pytest.raises(ValueError, match="File not found"):
            await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    file_path="/nonexistent/path/video.mp4",
                ),
                fake_ctx,
            )

    async def test_file_path_rejected_in_http_mode(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        tmp_path: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pathlib import Path

        from modelark_mcp.config.env import get_settings

        http_settings = get_settings().model_copy(update={"mcp_transport": "http"})
        monkeypatch.setattr("modelark_mcp.tools.media_upload.get_settings", lambda: http_settings)

        video_file = Path(str(tmp_path)) / "clip.mp4"
        video_file.write_bytes(b"data")

        with pytest.raises(ValueError, match="stdio transport"):
            await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    file_path=str(video_file),
                ),
                fake_ctx,
            )


class TestMediaUploadValidation:
    async def test_oversized_base64_rejected(self, test_env: None) -> None:
        oversized = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
        with pytest.raises(ValueError, match="exceeds limit"):
            MediaUploadInput(
                media_type="image",
                mime_type="image/png",
                data=oversized,
            )

    async def test_invalid_mime_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="not allowed"):
            MediaUploadInput(
                media_type="video",
                mime_type="text/plain",
                data=base64.b64encode(b"data").decode(),
            )

    async def test_both_data_and_file_path_rejected(self, test_env: None, tmp_path: object) -> None:
        from pathlib import Path

        f = Path(str(tmp_path)) / "f.mp4"
        f.write_bytes(b"data")
        with pytest.raises(ValueError, match="exactly one"):
            MediaUploadInput(
                media_type="video",
                mime_type="video/mp4",
                data=base64.b64encode(b"data").decode(),
                file_path=str(f),
            )

    async def test_neither_data_nor_file_path_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            MediaUploadInput(
                media_type="video",
                mime_type="video/mp4",
            )

    async def test_key_prefix_injection_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="key_prefix"):
            MediaUploadInput(
                media_type="video",
                mime_type="video/mp4",
                data=base64.b64encode(b"data").decode(),
                key_prefix="../../../etc/passwd",
            )


class TestMediaUploadErrors:
    async def test_no_tos_credentials_raises(
        self, test_env: None, fake_ctx: FakeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from modelark_mcp.config.env import get_settings

        no_tos = get_settings().model_copy(
            update={"tos_access_key": "", "tos_secret_key": "", "tos_bucket": ""}
        )
        monkeypatch.setattr("modelark_mcp.tools.media_upload.get_settings", lambda: no_tos)

        with pytest.raises(ValueError, match="TOS credentials"):
            await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    data=base64.b64encode(b"data").decode(),
                ),
                fake_ctx,
            )

    async def test_provider_error_returns_tool_result(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        mock_gw = _mock_gateway()
        mock_gw.upload_bytes = AsyncMock(
            side_effect=ProviderError(
                NormalizedProviderError(
                    provider="tos",
                    operation="upload",
                    http_status=500,
                    code="INTERNAL",
                    message="TOS internal error",
                    retryable=False,
                )
            )
        )

        with patch("modelark_mcp.tools.media_upload.TosGateway", return_value=mock_gw):
            result = await media_upload(
                MediaUploadInput(
                    media_type="video",
                    mime_type="video/mp4",
                    data=base64.b64encode(b"data").decode(),
                ),
                fake_ctx,
            )

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert result.structured_content is None
        assert "http_status=500" in result.content[0].text
        mock_gw.close.assert_called_once()
