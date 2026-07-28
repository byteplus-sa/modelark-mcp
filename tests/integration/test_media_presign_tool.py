"""Integration tests for the ``media_presign`` tool.

Uses the shared ``test_env`` / ``fake_ctx`` fixtures so the runtime
(budget ledger, provider limiters) is real.  The object-storage gateway is
mocked via ``patch`` so no SDK client or network is involved.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.tools.media_presign import (
    MediaPresignInput,
    MediaPresignOutput,
    media_presign,
)
from tests.fixtures.fake_context import FakeContext


def _mock_gateway() -> AsyncMock:
    gw = AsyncMock()
    gw.presign_get = AsyncMock(return_value="https://s3.example.com/fresh-presigned-url")
    gw.close = AsyncMock()
    return gw


_VALID_KEY = "references/video/abc-123-def"


class TestMediaPresignSuccess:
    async def test_presign_returns_fresh_url(self, test_env: None, fake_ctx: FakeContext) -> None:
        mock_gw = _mock_gateway()

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert isinstance(result, MediaPresignOutput)
        assert result.url == "https://s3.example.com/fresh-presigned-url"
        assert result.object_key == _VALID_KEY
        assert result.expires_at
        mock_gw.presign_get.assert_called_once_with(key=_VALID_KEY)
        mock_gw.close.assert_called_once()

    async def test_presign_with_custom_prefix_key(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        key = "uploads/2026/audio/my-file-uuid"
        mock_gw = _mock_gateway()

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=key),
                fake_ctx,
            )

        assert isinstance(result, MediaPresignOutput)
        assert result.object_key == key

    async def test_presign_progress_reported(self, test_env: None, fake_ctx: FakeContext) -> None:
        mock_gw = _mock_gateway()

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert (10, 100) in fake_ctx.progress_reports
        assert (30, 100) in fake_ctx.progress_reports
        assert (100, 100) in fake_ctx.progress_reports


class TestMediaPresignTosBackend:
    async def test_tos_backend_uses_tos_provider_slot(
        self, test_env: None, fake_ctx: FakeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from modelark_mcp.config.env import get_settings

        tos_settings = get_settings().model_copy(
            update={
                "tos_access_key": "ak-tos",
                "tos_secret_key": "sk-tos",  # pragma: allowlist secret
                "tos_bucket": "tos-bucket",
                "object_storage_backend": "tos",
            }
        )
        monkeypatch.setattr("modelark_mcp.tools.media_presign.get_settings", lambda: tos_settings)

        mock_gw = _mock_gateway()

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert isinstance(result, MediaPresignOutput)
        assert result.url == "https://s3.example.com/fresh-presigned-url"
        assert result.object_key == _VALID_KEY

    async def test_tos_backend_presign_after_upload_workflow(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        """End-to-end: upload then re-presign with the same gateway mock."""
        import base64

        from modelark_mcp.tools.media_upload import MediaUploadInput, media_upload

        upload_gw = AsyncMock()
        upload_gw.upload_bytes = AsyncMock(return_value=None)
        upload_gw.presign_get = AsyncMock(return_value="https://tos.example.com/original-url")
        upload_gw.close = AsyncMock()

        presign_gw = AsyncMock()
        presign_gw.presign_get = AsyncMock(return_value="https://tos.example.com/renewed-url")
        presign_gw.close = AsyncMock()

        data = base64.b64encode(b"fake-video-bytes").decode()

        with (
            patch(
                "modelark_mcp.tools.media_upload.make_object_storage_gateway",
                return_value=upload_gw,
            ),
            patch(
                "modelark_mcp.tools.media_presign.make_object_storage_gateway",
                return_value=presign_gw,
            ),
        ):
            upload_result = await media_upload(
                MediaUploadInput(media_type="video", mime_type="video/mp4", data=data),
                fake_ctx,
            )
            presign_result = await media_presign(
                MediaPresignInput(object_key=upload_result.object_key),
                fake_ctx,
            )

        assert upload_result.url == "https://tos.example.com/original-url"
        assert presign_result.url == "https://tos.example.com/renewed-url"
        assert presign_result.object_key == upload_result.object_key
        upload_gw.upload_bytes.assert_called_once()
        presign_gw.presign_get.assert_called_once_with(key=upload_result.object_key)


class TestMediaPresignS3Backend:
    async def test_s3_backend_uses_s3_provider_slot(
        self, test_env: None, fake_ctx: FakeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from modelark_mcp.config.env import get_settings

        s3_settings = get_settings().model_copy(
            update={
                "tos_access_key": "",
                "tos_secret_key": "",
                "tos_bucket": "",
                "s3_access_key": "ak-s3",
                "s3_secret_key": "sk-s3",  # pragma: allowlist secret
                "s3_bucket": "s3-bucket",
                "object_storage_backend": "s3",
            }
        )
        monkeypatch.setattr("modelark_mcp.tools.media_presign.get_settings", lambda: s3_settings)

        mock_gw = _mock_gateway()

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert isinstance(result, MediaPresignOutput)
        assert result.url == "https://s3.example.com/fresh-presigned-url"


class TestMediaPresignValidation:
    async def test_path_traversal_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="../../../etc/passwd")

    async def test_leading_slash_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="/references/video/abc")

    async def test_leading_dash_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="-references/video/abc")

    async def test_empty_segments_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="empty path segments"):
            MediaPresignInput(object_key="references//video/abc")

    async def test_trailing_slash_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="empty path segments"):
            MediaPresignInput(object_key="references/video/abc/")

    async def test_empty_key_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="")

    async def test_dot_in_key_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="references/video/file.txt")

    async def test_space_in_key_rejected(self, test_env: None) -> None:
        with pytest.raises(ValueError, match="object_key must contain only"):
            MediaPresignInput(object_key="references/video/my file")


class TestMediaPresignErrors:
    async def test_no_object_storage_credentials_raises(
        self, test_env: None, fake_ctx: FakeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from modelark_mcp.config.env import get_settings

        no_storage = get_settings().model_copy(
            update={
                "tos_access_key": "",
                "tos_secret_key": "",
                "tos_bucket": "",
                "s3_access_key": "",
                "s3_secret_key": "",
                "s3_bucket": "",
            }
        )
        monkeypatch.setattr("modelark_mcp.tools.media_presign.get_settings", lambda: no_storage)

        with pytest.raises(ValueError, match="Object storage is not configured"):
            await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

    async def test_provider_error_returns_tool_result(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        mock_gw = _mock_gateway()
        mock_gw.presign_get = AsyncMock(
            side_effect=ProviderError(
                NormalizedProviderError(
                    provider="s3",
                    operation="presign",
                    http_status=403,
                    code="AccessDenied",
                    message="Access denied",
                    retryable=False,
                )
            )
        )

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert result.structured_content is None
        assert "http_status=403" in result.content[0].text
        mock_gw.close.assert_called_once()

    async def test_provider_error_5xx_is_retryable(
        self, test_env: None, fake_ctx: FakeContext
    ) -> None:
        mock_gw = _mock_gateway()
        call_count = 0

        async def _fail_then_succeed(*, key: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError(
                    NormalizedProviderError(
                        provider="s3",
                        operation="presign",
                        http_status=500,
                        code="InternalError",
                        message="S3 internal error",
                        retryable=True,
                    )
                )
            return "https://s3.example.com/recovered-url"

        mock_gw.presign_get = _fail_then_succeed

        with patch(
            "modelark_mcp.tools.media_presign.make_object_storage_gateway",
            return_value=mock_gw,
        ):
            result = await media_presign(
                MediaPresignInput(object_key=_VALID_KEY),
                fake_ctx,
            )

        assert isinstance(result, MediaPresignOutput)
        assert result.url == "https://s3.example.com/recovered-url"
        assert call_count == 2
