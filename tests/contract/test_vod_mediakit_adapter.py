"""Contract tests for the provisional BytePlus VOD AI MediaKit adapter.

All responses are sanitized fixtures. No real provider request is made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod_mediakit.client import VodMediaKitGateway
from modelark_mcp.providers.vod_mediakit.enhancement import VodMediaKitEnhancementService
from modelark_mcp.providers.vod_mediakit.schemas import VodMediaKitEnhancementRequest

BASE_URL = "https://mediakit.ap-southeast-1.bytepluses.com/api/v1"
ENDPOINT = f"{BASE_URL}/tools/enhance-video"


@pytest.fixture
def service() -> VodMediaKitEnhancementService:
    """Create an isolated service with placeholder credentials."""
    return VodMediaKitEnhancementService(
        gateway=VodMediaKitGateway(
            api_key="test-mediakit-key",  # pragma: allowlist secret
            base_url=BASE_URL,
            timeout=10.0,
            connect_timeout=5.0,
        )
    )


def request() -> VodMediaKitEnhancementRequest:
    """Return the exact initial enhancement profile."""
    return VodMediaKitEnhancementRequest(
        video_url="https://media.example.com/source.mp4",
    )


class TestVodMediaKitRequestContract:
    """Verify the exact outbound mutation contract."""

    @respx.mock
    async def test_exact_path_headers_and_json(
        self,
        service: VodMediaKitEnhancementService,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        route = respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"output_url": "https://output.example.com/enhanced.mp4"},
                },
            )
        )

        await service.enhance(request())

        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer test-mediakit-key"
        assert sent.headers["Content-Type"] == "application/json"
        assert sent.headers["Accept"] == "application/json"
        assert json.loads(sent.content) == {
            "video_url": "https://media.example.com/source.mp4",
            "scene": "common",
            "tool_version": "professional",
            "resolution": "4k",
            "bitrate_level": "high",
            "fps": 24,
            "Project": "default",
        }
        assert "test-mediakit-key" not in capsys.readouterr().err

    def test_request_rejects_unknown_fields_and_non_https(self) -> None:
        with pytest.raises(ValidationError):
            VodMediaKitEnhancementRequest.model_validate(
                {"video_url": "https://media.example.com/in.mp4", "unknown": True}
            )
        with pytest.raises(ValidationError):
            VodMediaKitEnhancementRequest(video_url="http://media.example.com/in.mp4")


class TestVodMediaKitSuccessContract:
    """Verify conservative success-envelope parsing and normalization."""

    @respx.mock
    async def test_maps_data_envelope_and_preserves_metadata(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-header"},
                json={
                    "success": True,
                    "request_id": "body-request",
                    "data": {
                        "output_url": "https://output.example.com/enhanced.mp4",
                        "request_id": "nested-request",
                        "task_id": "task-1",
                        "status": "completed",
                        "mime_type": "video/mp4",
                        "expires_at": "2026-08-13T00:00:00Z",
                        "output_size_bytes": 12345,
                        "error": {"code": "WARN", "message": "provider warning"},
                    },
                },
            )
        )

        result = await service.enhance(request())

        assert result.status == "succeeded"
        assert result.request_id == "body-request"
        assert result.provider_log_id == "log-header"
        assert result.task_id == "task-1"
        assert str(result.output_url) == "https://output.example.com/enhanced.mp4"
        assert result.provider_status == "completed"
        assert result.mime_type == "video/mp4"
        assert result.expires_at == "2026-08-13T00:00:00Z"
        assert result.output_size_bytes == 12345
        assert result.failure_code == "WARN"
        assert result.failure_message == "provider warning"

    @respx.mock
    async def test_maps_observed_top_level_async_acceptance(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                headers={"x-tt-logid": "log-accepted"},
                json={
                    "success": True,
                    "task_id": "amk-tool-enhance-video-sanitized",
                    "request_id": "request-accepted",
                },
            )
        )

        result = await service.enhance(request())

        assert result.status == "accepted"
        assert result.task_id == "amk-tool-enhance-video-sanitized"
        assert result.request_id == "request-accepted"
        assert result.provider_log_id == "log-accepted"
        assert result.output_url is None

    @pytest.mark.parametrize("container", ["data", "result"])
    @pytest.mark.parametrize("url_field", ["output_url", "video_url", "url"])
    @respx.mock
    async def test_accepts_only_explicit_container_and_url_aliases(
        self,
        service: VodMediaKitEnhancementService,
        container: str,
        url_field: str,
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    container: {
                        url_field: "https://output.example.com/enhanced.mp4",
                        "id": "task-alias",
                        "content_type": "video/mp4",
                        "expiration": "2026-08-13T00:00:00Z",
                        "size": 99,
                        "future_field": "ignored",
                    },
                    "future_root_field": "ignored",
                },
            )
        )

        result = await service.enhance(request())

        assert result.task_id == "task-alias"
        assert result.mime_type == "video/mp4"
        assert result.output_size_bytes == 99

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"success": False, "error": {"message": "failed"}},
            {"success": True, "data": {}},
            {"success": True, "data": {"output_url": "http://output.example.com/out.mp4"}},
            {
                "success": True,
                "data": {
                    "output_url": "https://output.example.com/out.mp4",
                    "expires_at": "not-a-timestamp",
                },
            },
            {
                "success": True,
                "data": {"output_url": "https://output.example.com/a.mp4"},
                "result": {"output_url": "https://output.example.com/b.mp4"},
            },
        ],
    )
    @respx.mock
    async def test_rejects_unknown_or_malformed_success_bodies(
        self,
        service: VodMediaKitEnhancementService,
        body: dict[str, object],
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(200, json=body, headers={"x-tt-logid": "log-2"})
        )

        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())

        error = exc_info.value
        assert error.provider == "byteplus-vod-mediakit"
        assert error.code == "INVALID_RESPONSE"
        assert error.request_id == "log-2"
        assert error.retryable is False
        assert error.ambiguous_completion is False

    @respx.mock
    async def test_rejects_non_json_2xx(self, service: VodMediaKitEnhancementService) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(200, text="not-json"))
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.code == "INVALID_RESPONSE"


class TestVodMediaKitErrorContract:
    """Verify HTTP and transport failure normalization."""

    @respx.mock
    async def test_verified_unauthenticated_error(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                401,
                headers={"x-tt-logid": "log-401"},
                json={
                    "success": False,
                    "error": {
                        "code": "AuthenticationError",
                        "type": "Unauthorized",
                        "message": "The API key is missing or invalid.",
                    },
                },
            )
        )

        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())

        error = exc_info.value
        assert error.provider == "byteplus-vod-mediakit"
        assert error.http_status == 401
        assert error.code == "AuthenticationError"
        assert error.request_id == "log-401"
        assert error.retryable is False
        assert error.ambiguous_completion is False

    @respx.mock
    async def test_rate_limit_preserves_retry_hint(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "12.5"},
                json={"success": False, "error": {"message": "too many requests"}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.retryable is True
        assert exc_info.value.normalized.retry_after_seconds == 12.5
        assert exc_info.value.ambiguous_completion is False

    @respx.mock
    async def test_server_error_is_ambiguous_and_not_retryable(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                503,
                json={"success": False, "error": {"code": "BUSY", "message": "busy"}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.code == "BUSY"
        assert exc_info.value.retryable is False
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_error_message_redacts_urls(self, service: VodMediaKitEnhancementService) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(
                400,
                json={
                    "success": False,
                    "error": {
                        "message": "cannot fetch https://private.example.com/video.mp4?token=secret"
                    },
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert "private.example.com" not in exc_info.value.message
        assert "secret" not in exc_info.value.message

    @pytest.mark.parametrize(
        ("exception", "code"),
        [
            (httpx.TimeoutException("timed out"), "TIMEOUT"),
            (httpx.ReadError("connection lost"), "TRANSPORT_ERROR"),
        ],
    )
    @respx.mock
    async def test_transport_failures_are_ambiguous_and_not_retryable(
        self,
        service: VodMediaKitEnhancementService,
        exception: httpx.TransportError,
        code: str,
    ) -> None:
        respx.post(ENDPOINT).mock(side_effect=exception)
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.code == code
        assert exc_info.value.retryable is False
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_malformed_error_falls_back_without_body_leak(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(400, text="sensitive body"))
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.code == "HTTP_400"
        assert "sensitive body" not in exc_info.value.message

    @respx.mock
    async def test_redirect_is_not_accepted_as_success(
        self, service: VodMediaKitEnhancementService
    ) -> None:
        respx.post(ENDPOINT).mock(
            return_value=httpx.Response(307, headers={"Location": "https://other.example.com"})
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.enhance(request())
        assert exc_info.value.code == "HTTP_307"
        assert exc_info.value.retryable is False
