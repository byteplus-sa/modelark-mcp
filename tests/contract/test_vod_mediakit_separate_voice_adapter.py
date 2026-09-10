"""Contract tests for the BytePlus VOD AI MediaKit separate-voice adapter.

All responses are sanitized fixtures based on the official API reference. No
real provider request is made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod_mediakit.client import VodMediaKitGateway
from modelark_mcp.providers.vod_mediakit.schemas import VodMediaKitSeparateVoiceRequest
from modelark_mcp.providers.vod_mediakit.separate_voice import (
    VodMediaKitSeparateVoiceService,
)

BASE_URL = "https://mediakit.ap-southeast-1.bytepluses.com/api/v1"
SUBMIT_ENDPOINT = f"{BASE_URL}/tools/separate-voice"
TASK_PATH = "/tasks/task-1"
TASK_ENDPOINT = f"{BASE_URL}{TASK_PATH}"


@pytest.fixture
def service() -> VodMediaKitSeparateVoiceService:
    """Create an isolated service with placeholder credentials."""
    return VodMediaKitSeparateVoiceService(
        gateway=VodMediaKitGateway(
            api_key="test-mediakit-key",  # pragma: allowlist secret
            base_url=BASE_URL,
            timeout=10.0,
            connect_timeout=5.0,
        )
    )


def default_request() -> VodMediaKitSeparateVoiceRequest:
    """Return a documented two-way separation request."""
    return VodMediaKitSeparateVoiceRequest(video_url="https://media.example.com/clip.mp4")


class TestSeparateVoiceRequestContract:
    """Verify the exact outbound mutation contract."""

    @respx.mock
    async def test_exact_path_headers_and_json(
        self,
        service: VodMediaKitSeparateVoiceService,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        route = respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "amk-tool-separate-voice-1",
                    "request_id": "req-1",
                },
            )
        )

        await service.submit(default_request())

        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer test-mediakit-key"
        assert sent.headers["Content-Type"] == "application/json"
        assert sent.headers["Accept"] == "application/json"
        body = json.loads(sent.content)
        assert body["video_url"] == "https://media.example.com/clip.mp4"
        assert body["scene"] == "Audio"
        assert body["output_format"] == "aac"
        assert "audio_url" not in body
        assert "test-mediakit-key" not in capsys.readouterr().err

    def test_requires_exactly_one_source(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitSeparateVoiceRequest.model_validate({})
        with pytest.raises(ValidationError):
            VodMediaKitSeparateVoiceRequest.model_validate(
                {
                    "audio_url": "https://media.example.com/a.mp3",
                    "video_url": "https://media.example.com/b.mp4",
                }
            )

    def test_rejects_unknown_fields_and_non_https(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitSeparateVoiceRequest.model_validate(
                {"video_url": "https://media.example.com/in.mp4", "unknown": True}
            )
        with pytest.raises(ValidationError):
            VodMediaKitSeparateVoiceRequest(video_url="http://media.example.com/in.mp4")

    def test_scene_and_output_format_enums(self) -> None:
        req = VodMediaKitSeparateVoiceRequest(
            video_url="https://media.example.com/in.mp4", scene="Drama", output_format="flac"
        )
        assert req.scene == "Drama"
        assert req.output_format == "flac"
        with pytest.raises(ValidationError):
            VodMediaKitSeparateVoiceRequest(
                video_url="https://media.example.com/in.mp4", scene="Unknown"
            )


class TestSeparateVoiceSubmissionContract:
    """Verify async acceptance normalization."""

    @respx.mock
    async def test_accepted_submission(self, service: VodMediaKitSeparateVoiceService) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-1"},
                json={
                    "success": True,
                    "task_id": "amk-tool-separate-voice-1",
                    "request_id": "body-1",
                },
            )
        )

        result = await service.submit(default_request())

        assert result.status == "accepted"
        assert result.task_id == "amk-tool-separate-voice-1"
        assert result.request_id == "body-1"
        assert result.provider_log_id == "log-1"

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"success": False, "error": {"message": "failed"}},
            {"success": True},
            {"success": True, "task_id": ""},
        ],
    )
    @respx.mock
    async def test_rejects_unknown_or_malformed_submission_bodies(
        self,
        service: VodMediaKitSeparateVoiceService,
        body: dict[str, object],
    ) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(200, json=body, headers={"x-tt-logid": "log-2"})
        )

        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())

        error = exc_info.value
        assert error.provider == "byteplus-vod-mediakit"
        assert error.code == "INVALID_RESPONSE"
        assert error.retryable is False
        assert error.ambiguous_completion is False

    @respx.mock
    async def test_submit_timeout_is_ambiguous(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.retryable is False
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_submit_5xx_is_ambiguous(self, service: VodMediaKitSeparateVoiceService) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(
                503,
                json={"success": False, "error": {"code": "BUSY", "message": "busy"}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.ambiguous_completion is True
        assert exc_info.value.retryable is False


class TestSeparateVoiceTaskContract:
    """Verify poll-response normalization (statuses, tracks, timestamps, errors)."""

    @respx.mock
    async def test_completed_two_way_maps_to_succeeded(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-get"},
                json={
                    "success": True,
                    "task_id": "task-1",
                    "task_type": "separate-voice",
                    "status": "completed",
                    "result": {
                        "voice_audio_url": "https://output.example.com/voice.aac",
                        "background_audio_url": "https://output.example.com/background.aac",
                        "duration": 120.5,
                    },
                    "expires_at": 1780472196,
                    "created_at": 1780385775,
                    "finished_at": 1780385797,
                    "request_id": "req-get",
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "succeeded"
        assert result.task_id == "task-1"
        assert result.provider_status == "completed"
        assert result.request_id == "req-get"
        assert str(result.voice_url) == "https://output.example.com/voice.aac"
        assert str(result.background_url) == "https://output.example.com/background.aac"
        assert result.music_url is None
        assert result.sfx_url is None
        assert result.duration_seconds == 120.5
        assert result.created_at == "2026-06-02T07:36:15+00:00"
        assert result.finished_at == "2026-06-02T07:36:37+00:00"
        assert result.source_expires_at == "2026-06-03T07:36:36+00:00"

    @respx.mock
    async def test_completed_three_way_maps_tracks(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "completed",
                    "result": {
                        "voice_audio_url": "https://output.example.com/voice.aac",
                        "music_audio_url": "https://output.example.com/music.aac",
                        "sfx_audio_url": "https://output.example.com/sfx.aac",
                    },
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "succeeded"
        assert str(result.voice_url) == "https://output.example.com/voice.aac"
        assert result.background_url is None
        assert str(result.music_url) == "https://output.example.com/music.aac"
        assert str(result.sfx_url) == "https://output.example.com/sfx.aac"

    @respx.mock
    async def test_running_maps_to_processing(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "task_type": "separate-voice",
                    "status": "running",
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "processing"
        assert result.provider_status == "running"
        assert result.voice_url is None

    @respx.mock
    async def test_failed_maps_to_failed_with_sanitized_error(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "failed",
                    "error": {
                        "code": "DownloadFailed",
                        "message": "Failed to download file https://private.example.com/v.mp4?token=secret",
                        "param": "video_url",
                        "type": "TaskError",
                    },
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "failed"
        assert result.failure_code == "DownloadFailed"
        assert "private.example.com" not in (result.failure_message or "")
        assert "secret" not in (result.failure_message or "")

    @respx.mock
    async def test_failed_task_with_null_error_returns_fallback_message(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "task_id": "task-1", "status": "failed", "error": None},
            )
        )

        result = await service.get("task-1")

        assert result.status == "failed"
        assert result.failure_code is None
        assert result.failure_message
        assert len(result.failure_message) > 0

    @respx.mock
    async def test_unknown_status_fails_closed(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "expired",
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("task-1")
        assert exc_info.value.code == "INVALID_RESPONSE"
        assert exc_info.value.ambiguous_completion is False

    @respx.mock
    async def test_completed_without_track_fails_closed(
        self, service: VodMediaKitSeparateVoiceService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "completed",
                    "result": {"duration": 10},
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("task-1")
        assert exc_info.value.code == "INVALID_RESPONSE"

    @respx.mock
    async def test_get_429_is_retryable(self, service: VodMediaKitSeparateVoiceService) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"success": False, "error": {"message": "too many requests"}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("task-1")
        assert exc_info.value.retryable is True
        assert exc_info.value.ambiguous_completion is False
