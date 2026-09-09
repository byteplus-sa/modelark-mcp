"""Contract tests for MediaKit subtitle burn-in and precision erasure."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod_mediakit.client import VodMediaKitGateway
from modelark_mcp.providers.vod_mediakit.schemas import (
    VodMediaKitAddSubtitlesRequest,
    VodMediaKitEraseLocation,
    VodMediaKitRemoveSubtitlesRequest,
    VodMediaKitSubtitleCue,
    VodMediaKitSubtitleFilter,
    VodMediaKitTimeSegment,
    VodMediaKitTimeSegmentFilter,
)
from modelark_mcp.providers.vod_mediakit.subtitles import (
    VodMediaKitSubtitleBurnInService,
    VodMediaKitSubtitleRemovalService,
)

BASE_URL = "https://mediakit.ap-southeast-1.bytepluses.com/api/v1"


@pytest.fixture
def gateway() -> VodMediaKitGateway:
    return VodMediaKitGateway(
        api_key="test-mediakit-key",  # pragma: allowlist secret
        base_url=BASE_URL,
        timeout=10.0,
        connect_timeout=5.0,
    )


def add_request() -> VodMediaKitAddSubtitlesRequest:
    return VodMediaKitAddSubtitlesRequest(
        video_url="https://media.example.com/source.mp4",
        subtitles=[
            VodMediaKitSubtitleCue(
                subtitle_text="Hello",
                start_time=0.5,
                end_time=3.0,
            )
        ],
        subtitle_font_type="zhanku_kuaile",
        client_token="subtitle-job-1",
    )


def remove_request() -> VodMediaKitRemoveSubtitlesRequest:
    return VodMediaKitRemoveSubtitlesRequest(
        video_url="https://media.example.com/source.mp4",
        mode="Text",
        output_encode_mode="Quality",
        erase_ratio_location=[
            VodMediaKitEraseLocation(
                top_left_x=0.62,
                top_left_y=0.86,
                bottom_right_x=0.97,
                bottom_right_y=0.96,
            )
        ],
        time_segment_filter=VodMediaKitTimeSegmentFilter(
            mode="selected",
            segments=[VodMediaKitTimeSegment(start_time=10, end_time=60)],
        ),
        subtitle_filter=VodMediaKitSubtitleFilter(max_text_height_ratio=0.15),
        model_version="v5",
        project="default",
    )


class TestSubtitleRequestContracts:
    @respx.mock
    async def test_add_subtitles_exact_path_headers_and_body(
        self, gateway: VodMediaKitGateway
    ) -> None:
        route = respx.post(f"{BASE_URL}/tools/add-subtitle-to-video").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "task_id": "add-1", "request_id": "req-1"},
            )
        )
        service = VodMediaKitSubtitleBurnInService(gateway=gateway)

        await service.submit(add_request())

        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer test-mediakit-key"
        assert json.loads(sent.content) == {
            "video_url": "https://media.example.com/source.mp4",
            "subtitles": [{"subtitle_text": "Hello", "start_time": 0.5, "end_time": 3.0}],
            "subtitle_pos_preset": "bottom_center",
            "subtitle_font_size": 50,
            "subtitle_font_color": "#FFFFFFFF",
            "subtitle_font_type": "zhanku_kuaile",
            "client_token": "subtitle-job-1",
        }

    @respx.mock
    async def test_remove_subtitles_exact_path_and_body(self, gateway: VodMediaKitGateway) -> None:
        route = respx.post(f"{BASE_URL}/tools/erase-video-subtitle-pro").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "task_id": "remove-1", "request_id": "req-2"},
            )
        )
        service = VodMediaKitSubtitleRemovalService(gateway=gateway)

        await service.submit(remove_request())

        assert json.loads(route.calls.last.request.content) == {
            "video_url": "https://media.example.com/source.mp4",
            "mode": "Text",
            "output_encode_mode": "Quality",
            "erase_ratio_location": [
                {
                    "top_left_x": 0.62,
                    "top_left_y": 0.86,
                    "bottom_right_x": 0.97,
                    "bottom_right_y": 0.96,
                }
            ],
            "time_segment_filter": {
                "mode": "selected",
                "segments": [{"start_time": 10.0, "end_time": 60.0}],
            },
            "subtitle_filter": {"max_text_height_ratio": 0.15},
            "model_version": "v5",
            "Project": "default",
        }

    def test_add_subtitles_requires_content_and_valid_timing(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitAddSubtitlesRequest(video_url="https://media.example.com/source.mp4")
        with pytest.raises(ValidationError):
            VodMediaKitSubtitleCue(subtitle_text="bad", start_time=3, end_time=3)
        with pytest.raises(ValidationError):
            VodMediaKitSubtitleCue(subtitle_text="bad", start_time=-1, end_time=1)

    def test_add_subtitles_accepts_file_and_inline_content_together(self) -> None:
        request = VodMediaKitAddSubtitlesRequest(
            video_url="https://media.example.com/source.mp4",
            subtitle_url="https://media.example.com/subtitles.srt",
            subtitles=[VodMediaKitSubtitleCue(subtitle_text="ignored", start_time=0, end_time=1)],
        )
        assert request.subtitle_url is not None
        assert request.subtitles

    def test_style_and_callback_validation(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitAddSubtitlesRequest(
                video_url="https://media.example.com/source.mp4",
                subtitle_url="https://media.example.com/subtitles.srt",
                subtitle_font_color="#FFFFFF",
            )
        with pytest.raises(ValidationError):
            VodMediaKitAddSubtitlesRequest(
                video_url="https://media.example.com/source.mp4",
                subtitle_url="https://media.example.com/subtitles.srt",
                callback_args="界" * 257,
            )

    def test_erasure_nested_validation(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitEraseLocation(
                top_left_x=0.8,
                top_left_y=0.2,
                bottom_right_x=0.7,
                bottom_right_y=0.9,
            )
        with pytest.raises(ValidationError):
            VodMediaKitTimeSegment(start_time=5, end_time=1)
        with pytest.raises(ValidationError):
            VodMediaKitSubtitleFilter(
                min_text_height_ratio=0.2,
                max_text_height_ratio=0.1,
            )


@pytest.mark.parametrize(
    ("service_type", "request_factory", "task_id"),
    [
        (VodMediaKitSubtitleBurnInService, add_request, "add-1"),
        (VodMediaKitSubtitleRemovalService, remove_request, "remove-1"),
    ],
)
@respx.mock
async def test_submissions_normalize_acceptance(
    gateway: VodMediaKitGateway,
    service_type: type[VodMediaKitSubtitleBurnInService] | type[VodMediaKitSubtitleRemovalService],
    request_factory: object,
    task_id: str,
) -> None:
    path = (
        "/tools/add-subtitle-to-video"
        if service_type is VodMediaKitSubtitleBurnInService
        else "/tools/erase-video-subtitle-pro"
    )
    respx.post(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(
            200,
            headers={"x-tt-logid": "log-1"},
            json={"success": True, "task_id": task_id, "request_id": "req-1"},
        )
    )
    service = service_type(gateway=gateway)

    result = await service.submit(request_factory())  # type: ignore[operator]

    assert result.status == "accepted"
    assert result.task_id == task_id
    assert result.request_id == "req-1"
    assert result.provider_log_id == "log-1"


@pytest.mark.parametrize(
    ("service_type", "request_factory", "path"),
    [
        (VodMediaKitSubtitleBurnInService, add_request, "/tools/add-subtitle-to-video"),
        (
            VodMediaKitSubtitleRemovalService,
            remove_request,
            "/tools/erase-video-subtitle-pro",
        ),
    ],
)
@respx.mock
async def test_submission_timeout_is_ambiguous(
    gateway: VodMediaKitGateway,
    service_type: type[VodMediaKitSubtitleBurnInService] | type[VodMediaKitSubtitleRemovalService],
    request_factory: object,
    path: str,
) -> None:
    respx.post(f"{BASE_URL}{path}").mock(side_effect=httpx.TimeoutException("timeout"))
    service = service_type(gateway=gateway)

    with pytest.raises(ProviderError) as exc_info:
        await service.submit(request_factory())  # type: ignore[operator]

    assert exc_info.value.code == "TIMEOUT"
    assert exc_info.value.ambiguous_completion is True
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("service_type", "task_type", "resolution"),
    [
        (VodMediaKitSubtitleBurnInService, "add-subtitle-to-video", "1080p"),
        (VodMediaKitSubtitleRemovalService, "erase-video-subtitle-pro", None),
    ],
)
@respx.mock
async def test_completed_task_maps_to_succeeded(
    gateway: VodMediaKitGateway,
    service_type: type[VodMediaKitSubtitleBurnInService] | type[VodMediaKitSubtitleRemovalService],
    task_type: str,
    resolution: str | None,
) -> None:
    result_body: dict[str, object] = {
        "video_url": "https://output.example.com/subtitle.mp4",
        "duration": 15.5,
    }
    if resolution:
        result_body["resolution"] = resolution
    respx.get(f"{BASE_URL}/tasks/task-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "task_id": "task-1",
                "task_type": task_type,
                "status": "completed",
                "result": result_body,
                "expires_at": 1780472196,
                "created_at": 1780385775,
                "finished_at": 1780385797,
                "request_id": "req-get",
            },
        )
    )
    service = service_type(gateway=gateway)

    result = await service.get("task-1")

    assert result.status == "succeeded"
    assert str(result.output_url) == "https://output.example.com/subtitle.mp4"
    assert result.duration_seconds == 15.5
    assert result.resolution == resolution
    assert result.source_expires_at == "2026-06-03T07:36:36+00:00"


@pytest.mark.parametrize(
    ("service_type", "wrong_type"),
    [
        (VodMediaKitSubtitleBurnInService, "erase-video-subtitle-pro"),
        (VodMediaKitSubtitleRemovalService, "add-subtitle-to-video"),
    ],
)
@respx.mock
async def test_poll_rejects_mismatched_task_type(
    gateway: VodMediaKitGateway,
    service_type: type[VodMediaKitSubtitleBurnInService] | type[VodMediaKitSubtitleRemovalService],
    wrong_type: str,
) -> None:
    respx.get(f"{BASE_URL}/tasks/task-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "task_id": "task-1",
                "task_type": wrong_type,
                "status": "running",
            },
        )
    )

    with pytest.raises(ProviderError) as exc_info:
        await service_type(gateway=gateway).get("task-1")

    assert exc_info.value.code == "INVALID_RESPONSE"


@respx.mock
async def test_failed_task_sanitizes_provider_url(gateway: VodMediaKitGateway) -> None:
    respx.get(f"{BASE_URL}/tasks/task-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "task_id": "task-1",
                "task_type": "add-subtitle-to-video",
                "status": "failed",
                "error": {
                    "code": "DownloadFailed",
                    "message": "Failed https://private.example.com/file?token=secret",
                },
            },
        )
    )

    result = await VodMediaKitSubtitleBurnInService(gateway=gateway).get("task-1")

    assert result.status == "failed"
    assert result.failure_code == "DownloadFailed"
    assert "private.example.com" not in (result.failure_message or "")
    assert "secret" not in (result.failure_message or "")
