"""Contract tests for the LAS ASR adapter (speech-to-text).

Tests request building, submit/poll lifecycle, response parsing, and error
propagation. Uses respx to mock HTTP responses.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.las.asr import LasAsrService
from modelark_mcp.providers.las.client import LasGateway

LAS_BASE = "https://operator.las.ap-southeast-1.bytepluses.com"


@pytest.fixture
def service() -> LasAsrService:
    """Create a LasAsrService with a test gateway."""
    gateway = LasGateway(
        api_key="las-test-key",  # pragma: allowlist secret
        base_url=LAS_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )
    return LasAsrService(gateway=gateway)


class TestLasAsrRequestBuilding:
    """Tests for provider request construction."""

    def test_submit_request_with_defaults(self) -> None:
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        assert request.operator_id == "las_asr_pro"
        assert request.operator_version == "v1"
        assert request.data.audio.url == "https://example.com/audio.wav"
        assert request.data.audio.format == "wav"
        assert request.data.resource == "bigasr"
        assert request.data.request.model_name == "bigmodel"

    def test_submit_request_with_all_options(self) -> None:
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.mp3",
            audio_format="mp3",
            enable_punc=True,
            enable_itn=False,
            enable_speaker_info=True,
            enable_lid=True,
            show_utterances=True,
            show_words=True,
        )
        config = request.data.request
        assert config.enable_punc is True
        assert config.enable_itn is False
        assert config.enable_speaker_info is True
        assert config.enable_lid is True
        assert config.show_utterances is True
        assert config.show_words is True

    def test_submit_request_resource_for_pro(self) -> None:
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
            resource="seedasr",
        )
        assert request.data.resource == "seedasr"

    def test_submit_request_no_resource_for_standard(self) -> None:
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
            resource=None,
            operator_id="las_asr",
            operator_version="v2",
        )
        assert request.data.resource is None
        assert request.operator_id == "las_asr"
        assert request.operator_version == "v2"


class TestLasAsrDeriveOperatorVersion:
    """Tests for operator version derivation."""

    def test_pro_derives_v1(self) -> None:
        assert LasAsrService.derive_operator_version("las_asr_pro") == "v1"

    def test_standard_derives_v2(self) -> None:
        assert LasAsrService.derive_operator_version("las_asr") == "v2"

    def test_unknown_defaults_v1(self) -> None:
        assert LasAsrService.derive_operator_version("unknown_op") == "v1"


class TestLasAsrSubmit:
    """Tests for the submit endpoint."""

    @respx.mock
    async def test_success_returns_task_id(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/submit").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {
                        "task_id": "task-abc-123",
                        "task_status": "PENDING",
                        "business_code": "0",
                        "error_msg": "",
                        "request_id": "req-001",
                    }
                },
            )
        )
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        response, request_id = await service.submit(request)
        assert response.metadata.task_id == "task-abc-123"
        assert response.metadata.task_status == "PENDING"
        assert request_id == "req-001"

    @respx.mock
    async def test_bare_authorization_header(self, service: LasAsrService) -> None:
        route = respx.post(f"{LAS_BASE}/api/v1/submit").mock(
            return_value=httpx.Response(
                200,
                json={"metadata": {"task_id": "t1", "task_status": "PENDING"}},
            )
        )
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        await service.submit(request)
        assert route.calls.last.request.headers["Authorization"] == "las-test-key"

    @respx.mock
    async def test_provider_error_raised(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/submit").mock(
            return_value=httpx.Response(
                400,
                json={
                    "metadata": {
                        "task_id": "",
                        "task_status": "FAILED",
                        "business_code": "1001",
                        "error_msg": "Invalid audio format",
                        "request_id": "req-err",
                    }
                },
            )
        )
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(request)
        assert exc_info.value.http_status == 400
        assert exc_info.value.code == "1001"
        assert "Invalid audio format" in exc_info.value.message
        assert exc_info.value.request_id == "req-err"

    @respx.mock
    async def test_timeout_raises_ambiguous(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/submit").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(request)
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_connection_error_raises(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/submit").mock(side_effect=httpx.ConnectError("refused"))
        request = LasAsrService.build_submit_request(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.submit(request)
        assert exc_info.value.code == "CONNECTION_ERROR"


class TestLasAsrPoll:
    """Tests for the poll endpoint."""

    @respx.mock
    async def test_pending_status(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {
                        "task_id": "task-abc-123",
                        "task_status": "PENDING",
                        "business_code": "0",
                        "error_msg": "",
                        "request_id": "req-002",
                    }
                },
            )
        )
        response, request_id = await service.poll("task-abc-123")
        assert response.metadata.task_status == "PENDING"
        assert response.data is None
        assert request_id == "req-002"

    @respx.mock
    async def test_completed_with_utterances(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {
                        "task_id": "task-abc-123",
                        "task_status": "COMPLETED",
                        "business_code": "0",
                        "error_msg": "",
                        "request_id": "req-003",
                    },
                    "data": {
                        "audio_info": {"duration": 3575},
                        "result": {
                            "text": "Hello world.",
                            "utterances": [
                                {
                                    "text": "Hello world.",
                                    "start_time": 0,
                                    "end_time": 2000,
                                    "words": [
                                        {
                                            "text": "Hello",
                                            "confidence": 0.98,
                                            "start_time": 0,
                                            "end_time": 1000,
                                        },
                                        {
                                            "text": "world.",
                                            "confidence": 0.95,
                                            "start_time": 1000,
                                            "end_time": 2000,
                                        },
                                    ],
                                    "additions": {"speaker_id": "spk_0", "channel_id": "1"},
                                }
                            ],
                            "additions": {"duration": "3575"},
                        },
                    },
                },
            )
        )
        response, _ = await service.poll("task-abc-123")
        assert response.metadata.task_status == "COMPLETED"
        assert response.data is not None
        assert response.data.result is not None
        assert response.data.result.text == "Hello world."
        assert len(response.data.result.utterances) == 1
        utterance = response.data.result.utterances[0]
        assert utterance.text == "Hello world."
        assert utterance.start_time == 0
        assert utterance.end_time == 2000
        assert len(utterance.words) == 2
        assert utterance.words[0].text == "Hello"
        assert utterance.words[0].confidence == 0.98
        assert utterance.additions == {"speaker_id": "spk_0", "channel_id": "1"}
        assert response.data.audio_info is not None
        assert response.data.audio_info.duration == 3575

    @respx.mock
    async def test_completed_without_utterances(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {
                        "task_id": "task-abc-123",
                        "task_status": "COMPLETED",
                        "business_code": "0",
                        "error_msg": "",
                    },
                    "data": {
                        "result": {"text": "Plain text transcript."},
                    },
                },
            )
        )
        response, _ = await service.poll("task-abc-123")
        assert response.data is not None
        assert response.data.result is not None
        assert response.data.result.text == "Plain text transcript."
        assert response.data.result.utterances == []

    @respx.mock
    async def test_failed_status(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                200,
                json={
                    "metadata": {
                        "task_id": "task-abc-123",
                        "task_status": "FAILED",
                        "business_code": "5001",
                        "error_msg": "Audio processing failed",
                        "request_id": "req-err",
                    }
                },
            )
        )
        response, request_id = await service.poll("task-abc-123")
        assert response.metadata.task_status == "FAILED"
        assert response.metadata.business_code == "5001"
        assert response.metadata.error_msg == "Audio processing failed"
        assert request_id == "req-err"

    @respx.mock
    async def test_poll_provider_error_raised(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                404,
                json={
                    "metadata": {
                        "task_id": "",
                        "task_status": "FAILED",
                        "business_code": "4040",
                        "error_msg": "Task not found",
                        "request_id": "req-404",
                    }
                },
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.poll("nonexistent-task")
        assert exc_info.value.http_status == 404
        assert exc_info.value.code == "4040"
        assert "Task not found" in exc_info.value.message

    @respx.mock
    async def test_poll_timeout_raises_not_ambiguous(self, service: LasAsrService) -> None:
        respx.post(f"{LAS_BASE}/api/v1/poll").mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(ProviderError) as exc_info:
            await service.poll("task-abc-123")
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_poll_sends_operator_and_version(self, service: LasAsrService) -> None:
        route = respx.post(f"{LAS_BASE}/api/v1/poll").mock(
            return_value=httpx.Response(
                200,
                json={"metadata": {"task_id": "t1", "task_status": "PENDING"}},
            )
        )
        await service.poll("t1", operator_id="las_asr", operator_version="v2")
        import json

        body = json.loads(route.calls.last.request.content)
        assert body["operator_id"] == "las_asr"
        assert body["operator_version"] == "v2"
        assert body["task_id"] == "t1"
