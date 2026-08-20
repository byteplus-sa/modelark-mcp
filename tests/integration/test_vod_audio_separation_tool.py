"""Integration tests for the BytePlus VOD OpenAPI audio separation MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod.audio_separation import VodAudioSeparationService
from modelark_mcp.providers.vod.schemas import AudioSeparationSubmission, AudioSeparationTask
from modelark_mcp.security.auth_context import AuthContext
from modelark_mcp.tools.vod_get_audio_separation import (
    VodAudioSeparationTaskOutput,
    VodGetAudioSeparationInput,
    vod_get_audio_separation,
)
from modelark_mcp.tools.vod_separate_audio import (
    VodSeparateAudioInput,
    VodSeparateAudioOutput,
    vod_separate_audio,
)
from tests.fixtures.fake_context import FakeContext


async def _close(_self: VodAudioSeparationService) -> None:
    return None


def _submission() -> AudioSeparationSubmission:
    return AudioSeparationSubmission(status="accepted", request_id="req-1", run_id="run-1")


def _succeeded_task() -> AudioSeparationTask:
    return AudioSeparationTask(
        run_id="run-1",
        status="succeeded",
        provider_status="Success",
        request_id="req-get",
        duration_seconds=107.9,
        voice_file_name="hash_audiospeech.aac",
        voice_size_bytes=1787924,
        background_file_name="hash_background.aac",
        background_size_bytes=1787924,
    )


async def test_submit_accepts_and_records_ownership(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []

    async def submit(
        _self: VodAudioSeparationService, request: object
    ) -> AudioSeparationSubmission:
        captured.append(request)
        return _submission()

    monkeypatch.setattr(VodAudioSeparationService, "submit", submit)
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)
    runtime = fake_ctx.lifespan_context["runtime"]

    result = await vod_separate_audio(
        VodSeparateAudioInput(file_name="path/source.mp4", space_name="space", bucket_name="bkt"),
        fake_ctx,
    )

    assert isinstance(result, VodSeparateAudioOutput)
    assert result.status == "accepted"
    assert result.run_id == "run-1"
    assert result.request_id == "req-1"
    assert result.recommended_poll_after_ms == 3000
    assert captured
    assert await runtime.ownership_store.list_task_ids("vod", AuthContext()) == {"run-1"}


async def test_submit_serializes_direct_url_request(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    async def submit(
        _self: VodAudioSeparationService, request: object
    ) -> AudioSeparationSubmission:
        captured.append(request.model_dump(mode="json", by_alias=True, exclude_none=True))  # type: ignore[attr-defined]
        return _submission()

    monkeypatch.setattr(VodAudioSeparationService, "submit", submit)
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    await vod_separate_audio(
        VodSeparateAudioInput(file_name="path/source.mp4", space_name="space"), fake_ctx
    )

    body = captured[0]
    assert body["Input"] == {
        "Type": "DirectUrl",
        "DirectUrl": {"FileName": "path/source.mp4", "SpaceName": "space"},
    }
    assert body["Operation"]["Task"]["AudioExtract"]["Voice"] is True


async def test_submit_provider_error_returns_mcp_error(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ProviderError(
        NormalizedProviderError(
            provider="byteplus-vod",
            operation="start_audio_separation",
            http_status=400,
            code="InvalidParameter",
            message="Bad input.",
            retryable=False,
        )
    )
    monkeypatch.setattr(VodAudioSeparationService, "submit", AsyncMock(side_effect=error))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_separate_audio(VodSeparateAudioInput(file_name="path/source.mp4"), fake_ctx)

    assert isinstance(result, ToolResult)
    assert result.is_error is True


async def test_submit_missing_credential_raises(
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modelark_mcp.config.env import Settings

    settings = Settings(
        _env_file=None,
        BYTEPLUS_VOD_ACCESS_KEY_ID="",
        BYTEPLUS_VOD_SECRET_ACCESS_KEY="",
    )
    assert settings.has_vod is False

    runtime = fake_ctx.lifespan_context["runtime"]
    monkeypatch.setattr(runtime, "settings", settings)
    with pytest.raises(ValueError):
        await vod_separate_audio(VodSeparateAudioInput(file_name="path/source.mp4"), fake_ctx)


def test_separate_audio_input_validation() -> None:
    with pytest.raises(ValueError):
        VodSeparateAudioInput(file_name="")
    with pytest.raises(ValueError):
        VodSeparateAudioInput(file_name="a.mp4", space_name="")


async def test_poll_processing_returns_processing(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = AudioSeparationTask(
        run_id="run-1",
        status="processing",
        provider_status="Running",
        request_id="req-1",
    )
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=task))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_get_audio_separation(VodGetAudioSeparationInput(run_id="run-1"), fake_ctx)

    assert isinstance(result, VodAudioSeparationTaskOutput)
    assert result.status == "processing"
    assert result.provider_status == "Running"
    assert result.voice is None
    assert result.background is None


async def test_poll_succeeded_returns_tracks_without_urls(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=_succeeded_task()))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_get_audio_separation(VodGetAudioSeparationInput(run_id="run-1"), fake_ctx)

    assert isinstance(result, VodAudioSeparationTaskOutput)
    assert result.status == "succeeded"
    assert result.duration_seconds == 107.9
    assert result.voice is not None
    assert result.voice.file_name == "hash_audiospeech.aac"
    assert result.voice.size_bytes == 1787924
    assert result.voice.url is None
    assert result.background is not None
    assert result.background.file_name == "hash_background.aac"
    assert result.background.url is None


async def test_poll_succeeded_builds_playback_urls_from_input_domain(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=_succeeded_task()))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_get_audio_separation(
        VodGetAudioSeparationInput(run_id="run-1", playback_domain="play.example.com"),
        fake_ctx,
    )

    assert isinstance(result, VodAudioSeparationTaskOutput)
    assert result.voice is not None
    assert str(result.voice.url) == "https://play.example.com/hash_audiospeech.aac"
    assert result.background is not None
    assert str(result.background.url) == "https://play.example.com/hash_background.aac"


async def test_poll_succeeded_builds_playback_urls_from_settings_domain(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=_succeeded_task()))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)
    runtime = fake_ctx.lifespan_context["runtime"]
    runtime.settings.vod_playback_domain = "play.example.com"

    result = await vod_get_audio_separation(VodGetAudioSeparationInput(run_id="run-1"), fake_ctx)

    assert isinstance(result, VodAudioSeparationTaskOutput)
    assert result.voice is not None
    assert str(result.voice.url) == "https://play.example.com/hash_audiospeech.aac"


async def test_poll_rejects_invalid_playback_domain(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=_succeeded_task()))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    with pytest.raises(ValueError):
        await vod_get_audio_separation(
            VodGetAudioSeparationInput(
                run_id="run-1", playback_domain="https://play.example.com/path"
            ),
            fake_ctx,
        )


async def test_poll_failed_returns_error(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = AudioSeparationTask(
        run_id="run-1",
        status="failed",
        provider_status="Fail",
        failure_code="ExtractFailed",
        failure_message="VOD OpenAPI reported the separation task failed with status 'Fail'.",
    )
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(return_value=task))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_get_audio_separation(VodGetAudioSeparationInput(run_id="run-1"), fake_ctx)

    assert isinstance(result, VodAudioSeparationTaskOutput)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "ExtractFailed"
    assert result.voice is None


async def test_poll_provider_error_returns_mcp_error(
    test_env: None,
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ProviderError(
        NormalizedProviderError(
            provider="byteplus-vod",
            operation="get_audio_separation",
            http_status=429,
            code="RATE_LIMITED",
            message="Try later.",
            retryable=True,
        )
    )
    monkeypatch.setattr(VodAudioSeparationService, "get", AsyncMock(side_effect=error))
    monkeypatch.setattr(VodAudioSeparationService, "close", _close)

    result = await vod_get_audio_separation(VodGetAudioSeparationInput(run_id="run-1"), fake_ctx)

    assert isinstance(result, ToolResult)
    assert result.is_error is True
