"""Contract tests for the BytePlus VOD OpenAPI audio separation adapter.

All responses are sanitized fixtures based on the official feature guide. No
real provider request is made.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod.audio_separation import VodAudioSeparationService
from modelark_mcp.providers.vod.client import VodOpenApiGateway
from modelark_mcp.providers.vod.schemas import (
    VodDirectUrlInput,
    VodInputSpec,
    VodStartExecutionRequest,
)

BASE_URL = "https://vod.byteplusapi.com"
SUBMIT_ENDPOINT = f"{BASE_URL}/?Action=StartExecution&Version=2025-07-01"
GET_ENDPOINT = f"{BASE_URL}/?Action=GetExecution&Version=2025-07-01&RunId=run-1"


@pytest.fixture
def service() -> VodAudioSeparationService:
    return VodAudioSeparationService(
        gateway=VodOpenApiGateway(
            access_key_id="ak-test-vod",  # pragma: allowlist secret
            secret_access_key="sk-test-vod",  # pragma: allowlist secret
            region="ap-southeast-1",
            base_url=BASE_URL,
            timeout=10.0,
            connect_timeout=5.0,
        )
    )


def default_request() -> VodStartExecutionRequest:
    return VodStartExecutionRequest(
        input=VodInputSpec(
            type="DirectUrl",
            direct_url=VodDirectUrlInput(
                file_name="path/to/source.mp4",
                space_name="my-space",
                bucket_name="tos-vod-bucket",
            ),
        )
    )


class TestStartExecutionRequestContract:
    def test_serializes_exact_pascal_case_body(self) -> None:
        body = default_request().model_dump(mode="json", by_alias=True, exclude_none=True)
        assert body == {
            "Input": {
                "Type": "DirectUrl",
                "DirectUrl": {
                    "FileName": "path/to/source.mp4",
                    "SpaceName": "my-space",
                    "BucketName": "tos-vod-bucket",
                },
            },
            "Operation": {
                "Type": "Task",
                "Task": {
                    "Type": "AudioExtract",
                    "AudioExtract": {
                        "Voice": True,
                        "AudioOption": {"Format": "aac"},
                    },
                },
            },
        }

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            VodStartExecutionRequest.model_validate(
                {
                    "input": {
                        "type": "DirectUrl",
                        "direct_url": {"file_name": "a.mp4", "unknown": True},
                    }
                }
            )

    def test_direct_url_requires_file_name(self) -> None:
        with pytest.raises(ValidationError):
            VodDirectUrlInput(space_name="s")


class TestSubmitContract:
    @respx.mock
    async def test_submit_returns_run_id(
        self, service: VodAudioSeparationService, capsys: pytest.CaptureFixture[str]
    ) -> None:
        route = respx.post(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ResponseMetadata": {
                        "RequestId": "req-1",
                        "Action": "StartExecution",
                        "Version": "2025-07-01",
                    },
                    "Result": {"RunId": "p0:runsample"},
                },
            )
        )

        result = await service.submit(default_request())

        assert result.status == "accepted"
        assert result.run_id == "p0:runsample"
        assert result.request_id == "req-1"
        sent = route.calls.last.request
        assert sent.method == "POST"
        assert sent.url.query == b"Action=StartExecution&Version=2025-07-01"
        assert "authorization" in sent.headers
        assert "sk-test-vod" not in sent.headers["authorization"]
        body = json.loads(sent.content)
        assert body["Operation"]["Task"]["Type"] == "AudioExtract"
        assert "sk-test-vod" not in capsys.readouterr().err

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"ResponseMetadata": {}},
            {"ResponseMetadata": {}, "Result": {}},
            {"ResponseMetadata": {}, "Result": {"RunId": ""}},
        ],
    )
    @respx.mock
    async def test_rejects_malformed_submission(
        self, service: VodAudioSeparationService, body: dict[str, object]
    ) -> None:
        respx.post(f"{BASE_URL}/").mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.provider == "byteplus-vod"
        assert exc_info.value.code == "INVALID_RESPONSE"

    @respx.mock
    async def test_submit_timeout_is_ambiguous(self, service: VodAudioSeparationService) -> None:
        respx.post(f"{BASE_URL}/").mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.ambiguous_completion is True
        assert exc_info.value.retryable is False

    @respx.mock
    async def test_submit_http_error_normalizes_response_metadata(
        self, service: VodAudioSeparationService
    ) -> None:
        respx.post(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                400,
                json={
                    "ResponseMetadata": {
                        "RequestId": "req-err",
                        "Error": {"Code": "InvalidParameter", "Message": "bad input"},
                    }
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(default_request())
        assert exc_info.value.code == "InvalidParameter"
        assert exc_info.value.request_id == "req-err"
        assert exc_info.value.retryable is False


class TestGetContract:
    @respx.mock
    async def test_success_maps_to_succeeded(self, service: VodAudioSeparationService) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ResponseMetadata": {"RequestId": "req-get"},
                    "Result": {
                        "RunId": "run-1",
                        "Status": "Success",
                        "Output": {
                            "Type": "Task",
                            "Task": {
                                "Type": "AudioExtract",
                                "AudioExtract": {
                                    "Duration": 107.90168,
                                    "Voice": {
                                        "Size": "1787924",
                                        "FileName": "hash_audiospeech.aac",
                                    },
                                    "Background": {
                                        "Size": 1787924,
                                        "FileName": "hash_background.aac",
                                    },
                                },
                            },
                        },
                    },
                },
            )
        )

        result = await service.get("run-1")

        assert result.status == "succeeded"
        assert result.run_id == "run-1"
        assert result.provider_status == "Success"
        assert result.request_id == "req-get"
        assert result.duration_seconds == 107.90168
        assert result.voice_file_name == "hash_audiospeech.aac"
        assert result.voice_size_bytes == 1787924
        assert result.background_file_name == "hash_background.aac"
        assert result.background_size_bytes == 1787924

    @respx.mock
    async def test_success_without_voice_fails_closed(
        self, service: VodAudioSeparationService
    ) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ResponseMetadata": {"RequestId": "req-get"},
                    "Result": {
                        "RunId": "run-1",
                        "Status": "Success",
                        "Output": {
                            "Type": "Task",
                            "Task": {"Type": "AudioExtract", "AudioExtract": {}},
                        },
                    },
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("run-1")
        assert exc_info.value.code == "INVALID_RESPONSE"

    @pytest.mark.parametrize("status", ["Fail", "Failed", "Error", "Terminated", "Timeout"])
    @respx.mock
    async def test_failure_statuses_map_to_failed(
        self, service: VodAudioSeparationService, status: str
    ) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ResponseMetadata": {"RequestId": "req-get"},
                    "Result": {"RunId": "run-1", "Status": status, "Code": "ExtractFailed"},
                },
            )
        )
        result = await service.get("run-1")
        assert result.status == "failed"
        assert result.failure_code == "ExtractFailed"

    @respx.mock
    async def test_inflight_status_maps_to_processing(
        self, service: VodAudioSeparationService
    ) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "ResponseMetadata": {"RequestId": "req-get"},
                    "Result": {"RunId": "run-1", "Status": "Running"},
                },
            )
        )
        result = await service.get("run-1")
        assert result.status == "processing"
        assert result.provider_status == "Running"

    @respx.mock
    async def test_missing_status_fails_closed(self, service: VodAudioSeparationService) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                200,
                json={"ResponseMetadata": {"RequestId": "req-get"}, "Result": {"RunId": "run-1"}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("run-1")
        assert exc_info.value.code == "INVALID_RESPONSE"

    @respx.mock
    async def test_get_429_is_retryable(self, service: VodAudioSeparationService) -> None:
        respx.get(f"{BASE_URL}/").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"ResponseMetadata": {"Error": {"Message": "too many requests"}}},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.get("run-1")
        assert exc_info.value.retryable is True
        assert exc_info.value.ambiguous_completion is False
