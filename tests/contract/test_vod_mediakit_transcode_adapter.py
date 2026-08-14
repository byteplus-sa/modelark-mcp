"""Contract tests for the BytePlus VOD AI MediaKit transcode adapter.

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
from modelark_mcp.providers.vod_mediakit.schemas import (
    VodMediaKitTranscodeRequest,
    VodMediaKitTranscodeVideoOptions,
)
from modelark_mcp.providers.vod_mediakit.transcode import VodMediaKitTranscodeService

BASE_URL = "https://mediakit.ap-southeast-1.bytepluses.com/api/v1"
SUBMIT_ENDPOINT = f"{BASE_URL}/tools/transcode-video"
TASK_PATH = "/tasks/task-1"
TASK_ENDPOINT = f"{BASE_URL}{TASK_PATH}"


@pytest.fixture
def service() -> VodMediaKitTranscodeService:
    """Create an isolated service with placeholder credentials."""
    return VodMediaKitTranscodeService(
        gateway=VodMediaKitGateway(
            api_key="test-mediakit-key",  # pragma: allowlist secret
            base_url=BASE_URL,
            timeout=10.0,
            connect_timeout=5.0,
        )
    )


def default_request() -> VodMediaKitTranscodeRequest:
    """Return the exact verified portrait-to-720x720 profile."""
    return VodMediaKitTranscodeRequest(
        video_url="https://media.example.com/portrait.mp4",
        video=VodMediaKitTranscodeVideoOptions(
            scale_type=2,
            scale_width=720,
            scale_height=720,
            scale_mode=2,
        ),
    )


class TestTranscodeRequestContract:
    """Verify the exact outbound mutation contract."""

    @respx.mock
    async def test_exact_path_headers_and_json(
        self,
        service: VodMediaKitTranscodeService,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        route = respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "amk-tool-transcode-video-1",
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
        assert body["video_url"] == "https://media.example.com/portrait.mp4"
        assert body["container_format"] == "MP4"
        assert body["video"] == {
            "codec": "h264",
            "scale_type": 2,
            "scale_mode": 2,
            "scale_width": 720,
            "scale_height": 720,
            "bitrate_mode": "crf",
            "bitrate_crf": 25,
            "bitrate_kbps": 2000,
            "fps_mode": "vfr",
            "is_hdr_to_sdr": True,
        }
        assert "test-mediakit-key" not in capsys.readouterr().err

    def test_rejects_unknown_fields_and_non_https(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeRequest.model_validate(
                {"video_url": "https://media.example.com/in.mp4", "unknown": True}
            )
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeRequest(video_url="http://media.example.com/in.mp4")

    def test_scale_validation_rules(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeVideoOptions(scale_type=2, scale_mode=2)
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeVideoOptions(scale_type=1, scale_mode=2)
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeVideoOptions(
                scale_type=1, scale_short=720, scale_long=1280, scale_width=720
            )
        opts = VodMediaKitTranscodeVideoOptions(scale_type=1, scale_short=720, scale_long=1280)
        assert opts.scale_short == 720

    def test_follow_source_ignores_scale_fields(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitTranscodeVideoOptions(scale_type=0, scale_width=720)


class TestTranscodeSubmissionContract:
    """Verify async acceptance normalization."""

    @respx.mock
    async def test_accepted_submission(self, service: VodMediaKitTranscodeService) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-1"},
                json={
                    "success": True,
                    "task_id": "amk-tool-transcode-video-1",
                    "request_id": "body-1",
                },
            )
        )

        result = await service.submit(default_request())

        assert result.status == "accepted"
        assert result.task_id == "amk-tool-transcode-video-1"
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
        service: VodMediaKitTranscodeService,
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
    async def test_submit_timeout_is_ambiguous(self, service: VodMediaKitTranscodeService) -> None:
        respx.post(SUBMIT_ENDPOINT).mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.retryable is False
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_submit_5xx_is_ambiguous(self, service: VodMediaKitTranscodeService) -> None:
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


class TestTranscodeTaskContract:
    """Verify poll-response normalization (statuses, timestamps, errors)."""

    @respx.mock
    async def test_completed_maps_to_succeeded_with_epoch_timestamps(
        self, service: VodMediaKitTranscodeService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-get"},
                json={
                    "success": True,
                    "task_id": "task-1",
                    "task_type": "transcode-video",
                    "status": "completed",
                    "result": {
                        "duration": 15.07,
                        "resolution": "720p",
                        "video_codec": "h264",
                        "video_url": "https://output.example.com/transcoded.mp4",
                    },
                    "expires_at": 1780472196,
                    "created_at": 1780385775,
                    "finished_at": 1780385797,
                    "request_id": "req-get",
                    "queue_id": "default",
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "succeeded"
        assert result.task_id == "task-1"
        assert result.provider_status == "completed"
        assert result.request_id == "req-get"
        assert str(result.output_url) == "https://output.example.com/transcoded.mp4"
        assert result.duration_seconds == 15.07
        assert result.resolution == "720p"
        assert result.video_codec == "h264"
        assert result.created_at == "2026-06-02T07:36:15+00:00"
        assert result.finished_at == "2026-06-02T07:36:37+00:00"
        assert result.source_expires_at == "2026-06-03T07:36:36+00:00"

    @respx.mock
    async def test_running_maps_to_processing(self, service: VodMediaKitTranscodeService) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "task_type": "transcode-video",
                    "status": "running",
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "processing"
        assert result.provider_status == "running"
        assert result.output_url is None

    @respx.mock
    async def test_failed_maps_to_failed_with_sanitized_error(
        self, service: VodMediaKitTranscodeService
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
    async def test_iso8601_timestamps_accepted(self, service: VodMediaKitTranscodeService) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "completed",
                    "result": {"video_url": "https://output.example.com/out.mp4"},
                    "expires_at": "2026-08-13T00:00:00Z",
                },
            )
        )

        result = await service.get("task-1")

        assert result.status == "succeeded"
        assert result.source_expires_at == "2026-08-13T00:00:00+00:00"

    @respx.mock
    async def test_unknown_status_fails_closed(self, service: VodMediaKitTranscodeService) -> None:
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
    async def test_completed_without_url_fails_closed(
        self, service: VodMediaKitTranscodeService
    ) -> None:
        respx.get(TASK_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "task-1",
                    "status": "completed",
                    "result": {},
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("task-1")
        assert exc_info.value.code == "INVALID_RESPONSE"

    @respx.mock
    async def test_get_429_is_retryable(self, service: VodMediaKitTranscodeService) -> None:
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
