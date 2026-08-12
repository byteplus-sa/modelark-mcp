"""Integration tests for the VOD AI MediaKit MCP tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.artifacts.store import ArtifactPersistenceError
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod_mediakit.enhancement import VodMediaKitEnhancementService
from modelark_mcp.providers.vod_mediakit.schemas import EnhancementSubmission
from modelark_mcp.security.auth_context import AuthContext
from modelark_mcp.tools.vod_enhance_video import (
    VodEnhanceVideoInput,
    VodEnhanceVideoOutput,
    vod_enhance_video,
)
from tests.fixtures.fake_context import FakeContext


async def _close(_self: VodMediaKitEnhancementService) -> None:
    return None


def _submission() -> EnhancementSubmission:
    return EnhancementSubmission(
        status="succeeded",
        request_id="log-1",
        provider_log_id="provider-log-1",
        task_id="task-1",
        output_url="https://tos-ap-southeast.bytepluses.com/enhanced.mp4",
        mime_type="video/mp4",
        expires_at="2026-08-13T00:00:00Z",
        output_size_bytes=123,
        provider_status="completed",
    )


async def test_success_without_persistence_preserves_provider_url(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    async def enhance(
        _self: VodMediaKitEnhancementService, request: object
    ) -> EnhancementSubmission:
        captured.append(request)
        return _submission()

    monkeypatch.setattr(VodMediaKitEnhancementService, "enhance", enhance)
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)
    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4", persist=False), fake_ctx
    )

    assert isinstance(result, VodEnhanceVideoOutput)
    assert str(result.source_url) == "https://tos-ap-southeast.bytepluses.com/enhanced.mp4"
    assert result.persistence == "not_requested"
    assert result.video is None
    assert result.estimated_cost_usd is None
    assert captured


async def test_accepted_task_is_owned_and_not_persisted(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission = EnhancementSubmission(
        status="accepted",
        request_id="request-1",
        provider_log_id="log-1",
        task_id="amk-tool-enhance-video-1",
    )
    monkeypatch.setattr(
        VodMediaKitEnhancementService, "enhance", AsyncMock(return_value=submission)
    )
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)
    runtime = fake_ctx.lifespan_context["runtime"]
    copy = AsyncMock()
    monkeypatch.setattr(runtime.artifact_store, "copy_from_trusted_url", copy)

    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4"), fake_ctx
    )

    assert isinstance(result, VodEnhanceVideoOutput)
    assert result.status == "accepted"
    assert result.request_id == "request-1"
    assert result.provider_log_id == "log-1"
    assert result.task_id == "amk-tool-enhance-video-1"
    assert result.source_url is None
    assert result.persistence == "not_applicable"
    assert result.video is None
    assert await runtime.ownership_store.list_task_ids("vod-mediakit", AuthContext()) == {
        "amk-tool-enhance-video-1"
    }
    copy.assert_not_awaited()


async def test_successful_persistence_returns_artifact(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = ArtifactRef(
        id="artifact-1",
        uri="seed-media://artifacts/artifact-1",
        media_type="video",
        mime_type="video/mp4",
        bytes=123,
        sha256="abc",
        created_at="2026-08-12T00:00:00Z",
    )
    monkeypatch.setattr(
        VodMediaKitEnhancementService, "enhance", AsyncMock(return_value=_submission())
    )
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)
    store = fake_ctx.lifespan_context["runtime"].artifact_store
    copy = AsyncMock(return_value=ref)
    monkeypatch.setattr(store, "copy_from_trusted_url", copy)

    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4"), fake_ctx
    )

    assert isinstance(result, VodEnhanceVideoOutput)
    assert result.persistence == "persisted"
    assert result.video == ref
    copy.assert_awaited_once()


async def test_persistence_failure_does_not_erase_provider_success(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        VodMediaKitEnhancementService, "enhance", AsyncMock(return_value=_submission())
    )
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)
    store = fake_ctx.lifespan_context["runtime"].artifact_store
    monkeypatch.setattr(
        store,
        "copy_from_trusted_url",
        AsyncMock(
            side_effect=ArtifactPersistenceError(
                "output_too_large", "Output exceeds the artifact limit.", retryable=False
            )
        ),
    )

    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4"), fake_ctx
    )

    assert isinstance(result, VodEnhanceVideoOutput)
    assert result.status == "succeeded"
    assert result.persistence == "failed"
    assert result.persistence_issue is not None
    assert result.persistence_issue.code == "output_too_large"
    assert result.persistence_issue.artifact_limit_bytes == 209_715_200


async def test_unexpected_storage_failure_does_not_erase_provider_success(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        VodMediaKitEnhancementService, "enhance", AsyncMock(return_value=_submission())
    )
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)
    store = fake_ctx.lifespan_context["runtime"].artifact_store
    monkeypatch.setattr(
        store, "copy_from_trusted_url", AsyncMock(side_effect=RuntimeError("backend detail"))
    )

    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4"), fake_ctx
    )

    assert isinstance(result, VodEnhanceVideoOutput)
    assert result.status == "succeeded"
    assert result.persistence == "failed"
    assert result.persistence_issue is not None
    assert result.persistence_issue.code == "storage_failed"
    assert "backend detail" not in result.persistence_issue.message


async def test_provider_error_returns_mcp_error(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ProviderError(
        NormalizedProviderError(
            provider="byteplus-vod-mediakit",
            operation="enhance_video",
            http_status=429,
            code="RATE_LIMITED",
            message="Try later.",
            retryable=True,
        )
    )
    monkeypatch.setattr(VodMediaKitEnhancementService, "enhance", AsyncMock(side_effect=error))
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", _close)

    result = await vod_enhance_video(
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4"), fake_ctx
    )

    assert isinstance(result, ToolResult)
    assert result.is_error is True


def test_input_rejects_unverified_profile_values() -> None:
    with pytest.raises(ValueError):
        VodEnhanceVideoInput(video_url="https://example.com/input.mp4", resolution="1080p")  # type: ignore[arg-type]
