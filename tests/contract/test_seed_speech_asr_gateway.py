"""Contract tests for the Seed Speech ASR HTTP gateway and service.

Covers submit/query success, non-terminal polling, error normalization
(4xx/5xx/malformed JSON), transport error conversion (timeout, connection,
transport), JSON decode failure on 2xx, and gateway lifecycle (close).

Uses ``respx`` to mock ``httpx.AsyncClient`` requests — no real network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.seed_speech.asr import SeedSpeechAsrService
from modelark_mcp.providers.seed_speech.asr_http import SeedSpeechAsrHttpGateway

ASR_BASE = "https://voice.test.example.com"


@pytest.fixture
def asr_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set env vars so lazily-created gateways use the test base URL."""
    from modelark_mcp.config.env import get_settings

    monkeypatch.setenv("BYTEPLUS_SEED_SPEECH_API_KEY", "sk-test-asr")
    monkeypatch.setenv("SEED_SPEECH_ASR_BASE_URL", ASR_BASE)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def gateway() -> SeedSpeechAsrHttpGateway:
    return SeedSpeechAsrHttpGateway(
        api_key="sk-test-asr",  # pragma: allowlist secret
        base_url=ASR_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )


def _asr_result_body() -> dict[str, Any]:
    return {
        "result": {
            "text": "hello world",
            "utterances": [
                {
                    "text": "hello world",
                    "start_time": 0,
                    "end_time": 1500,
                    "words": [
                        {"text": "hello", "confidence": 0.99, "start_time": 0, "end_time": 500},
                        {"text": "world", "confidence": 0.98, "start_time": 600, "end_time": 1500},
                    ],
                }
            ],
        },
        "audio_info": {"duration": 1500},
    }


class TestSeedSpeechAsrGatewaySubmit:
    """Tests for submit request shape and response handling."""

    @respx.mock
    async def test_submit_success(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        route = respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        task_id = await gateway.submit(
            audio_data="aGVsbG8=",
            audio_format="wav",
            language="en-US",
            request_id="req-001",
        )
        assert task_id == "req-001"
        assert route.called

        request = route.calls.last.request
        assert request.headers["x-api-key"] == "sk-test-asr"
        assert request.headers["X-Api-Resource-Id"] == "volc.seedasr.auc"
        assert request.headers["X-Api-Request-Id"] == "req-001"
        assert request.headers["X-Api-Sequence"] == "-1"

    @respx.mock
    async def test_submit_with_url(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        await gateway.submit(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
            request_id="req-url",
        )

    @respx.mock
    async def test_submit_400_error(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(
                400,
                json={"code": 1001, "message": "invalid audio format"},
                headers={"X-Tt-Logid": "log-400"},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await gateway.submit(audio_data="aGVsbG8=", request_id="req-err")
        assert exc_info.value.http_status == 400
        assert exc_info.value.code == "1001"
        assert not exc_info.value.retryable

    @respx.mock
    async def test_submit_500_retryable(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(500, json={"code": 5000, "message": "internal"})
        )
        with pytest.raises(ProviderError) as exc_info:
            await gateway.submit(audio_data="aGVsbG8=", request_id="req-500")
        assert exc_info.value.http_status == 500
        assert exc_info.value.retryable


class TestSeedSpeechAsrGatewayQuery:
    """Tests for query polling and response parsing."""

    @respx.mock
    async def test_query_returns_result(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                200,
                json=_asr_result_body(),
            )
        )
        result = await gateway.query(task_id="req-001", sequence=0)
        assert result is not None
        assert result["result"]["text"] == "hello world"

    @respx.mock
    async def test_query_non_terminal_returns_none(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                200,
                json={},
                headers={"x-api-status-code": "20000001"},
            )
        )
        result = await gateway.query(task_id="req-001", sequence=0)
        assert result is None

    @respx.mock
    async def test_query_non_terminal_45000000(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                200,
                json={},
                headers={"x-api-status-code": "45000000"},
            )
        )
        result = await gateway.query(task_id="req-001", sequence=1)
        assert result is None

    @respx.mock
    async def test_query_2xx_non_json_raises_provider_error(
        self, gateway: SeedSpeechAsrHttpGateway
    ) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        with pytest.raises(ProviderError) as exc_info:
            await gateway.query(task_id="req-001", sequence=0)
        assert exc_info.value.http_status == 200

    @respx.mock
    async def test_query_400_error(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                400,
                json={"code": 2001, "message": "task not found"},
            )
        )
        with pytest.raises(ProviderError) as exc_info:
            await gateway.query(task_id="missing", sequence=0)
        assert exc_info.value.http_status == 400
        assert not exc_info.value.retryable


class TestSeedSpeechAsrGatewayErrorNormalization:
    """Tests for normalize_error, normalize_timeout, normalize_connection_error."""

    @respx.mock
    async def test_malformed_json_body(self, gateway: SeedSpeechAsrHttpGateway) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(500, content=b"garbage")
        )
        with pytest.raises(ProviderError) as exc_info:
            await gateway.submit(audio_data="aGVsbG8=", request_id="req-bad")
        assert "garbage" in exc_info.value.message

    def test_normalize_timeout(self) -> None:
        error = SeedSpeechAsrHttpGateway.normalize_timeout("submit_asr")
        assert error.code == "TIMEOUT"
        assert error.ambiguous_completion is True
        assert not error.retryable

    def test_normalize_connection_error(self) -> None:
        exc = httpx.ConnectError("connection refused")
        error = SeedSpeechAsrHttpGateway.normalize_connection_error("query_asr", exc)
        assert error.code == "CONNECTION_ERROR"
        assert error.retryable
        assert "connection refused" in error.message

    def test_normalize_transport_error(self) -> None:
        exc = httpx.ReadError("read failed")
        error = SeedSpeechAsrHttpGateway.normalize_transport_error("submit_asr", exc)
        assert error.code == "TRANSPORT_ERROR"
        assert error.retryable

    def test_extract_request_id(self) -> None:
        response = httpx.Response(200, json={}, headers={"X-Tt-Logid": "log-abc"})
        assert SeedSpeechAsrHttpGateway.extract_request_id(response) == "log-abc"

    def test_extract_request_id_lowercase(self) -> None:
        response = httpx.Response(200, json={}, headers={"x-tt-logid": "log-xyz"})
        assert SeedSpeechAsrHttpGateway.extract_request_id(response) == "log-xyz"

    def test_extract_request_id_missing(self) -> None:
        response = httpx.Response(200, json={})
        assert SeedSpeechAsrHttpGateway.extract_request_id(response) is None


class TestSeedSpeechAsrServiceTransportErrors:
    """Tests that transport errors are normalized to ProviderError (fix #1)."""

    @respx.mock
    async def test_submit_timeout_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=0.01,
                connect_timeout=0.01,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(audio_bytes=b"fake", audio_format="wav")
        assert exc_info.value.code == "TIMEOUT"
        assert "submit_asr" in exc_info.value.message

    @respx.mock
    async def test_submit_connect_error_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(audio_bytes=b"fake", audio_format="wav")
        assert exc_info.value.code == "CONNECTION_ERROR"
        assert exc_info.value.retryable

    @respx.mock
    async def test_submit_transport_error_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            side_effect=httpx.ReadError("read failed")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(audio_bytes=b"fake", audio_format="wav")
        assert exc_info.value.code == "TRANSPORT_ERROR"
        assert exc_info.value.retryable

    @respx.mock
    async def test_query_timeout_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=0.01,
                connect_timeout=0.01,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(
                audio_bytes=b"fake", audio_format="wav", poll_interval=0.0, poll_max=1.0
            )
        assert exc_info.value.code == "TIMEOUT"
        assert "query_asr" in exc_info.value.message

    @respx.mock
    async def test_query_connect_error_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(
                audio_bytes=b"fake", audio_format="wav", poll_interval=0.0, poll_max=1.0
            )
        assert exc_info.value.code == "CONNECTION_ERROR"

    @respx.mock
    async def test_query_json_decode_error_raises_provider_error(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(200, content=b"not json at all")
        )
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(
                audio_bytes=b"fake", audio_format="wav", poll_interval=0.0, poll_max=1.0
            )
        assert exc_info.value.http_status == 200


class TestSeedSpeechAsrServiceTranscribe:
    """Tests for the transcribe happy path and result mapping."""

    @respx.mock
    async def test_transcribe_success(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(200, json=_asr_result_body())
        )
        result, log_id = await service.transcribe(
            audio_bytes=b"fake audio",
            audio_format="wav",
            poll_interval=0.0,
            poll_max=5.0,
        )
        assert result.text == "hello world"
        assert len(result.utterances) == 1
        assert result.utterances[0].text == "hello world"
        assert len(result.utterances[0].words) == 2
        assert result.utterances[0].words[0].text == "hello"
        assert result.utterances[0].words[0].confidence == 0.99
        assert result.duration_ms == 1500
        assert log_id is None

    @respx.mock
    async def test_transcribe_with_url(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(200, json=_asr_result_body())
        )
        result, _ = await service.transcribe(
            audio_url="https://example.com/audio.wav",
            audio_format="wav",
            poll_interval=0.0,
            poll_max=5.0,
        )
        assert result.text == "hello world"

    @respx.mock
    async def test_transcribe_polls_until_ready(self) -> None:
        service = SeedSpeechAsrService(
            gateway=SeedSpeechAsrHttpGateway(
                api_key="sk-test",  # pragma: allowlist secret
                base_url=ASR_BASE,
                timeout=10.0,
                connect_timeout=5.0,
            )
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        route = respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query")
        route.mock(
            side_effect=[
                httpx.Response(200, json={}, headers={"x-api-status-code": "20000001"}),
                httpx.Response(200, json=_asr_result_body()),
            ]
        )
        result, _ = await service.transcribe(
            audio_bytes=b"fake",
            audio_format="wav",
            poll_interval=0.0,
            poll_max=5.0,
        )
        assert result.text == "hello world"
        assert route.call_count == 2

    async def test_transcribe_timeout_poll_max(self) -> None:
        gateway_mock = AsyncMock(spec=SeedSpeechAsrHttpGateway)
        gateway_mock.submit = AsyncMock(return_value="req-001")
        gateway_mock.query = AsyncMock(return_value=None)
        gateway_mock.normalize_timeout = SeedSpeechAsrHttpGateway.normalize_timeout
        gateway_mock.normalize_connection_error = (
            SeedSpeechAsrHttpGateway.normalize_connection_error
        )
        gateway_mock.normalize_transport_error = SeedSpeechAsrHttpGateway.normalize_transport_error

        service = SeedSpeechAsrService(gateway=gateway_mock)
        with pytest.raises(ProviderError) as exc_info:
            await service.transcribe(
                audio_bytes=b"fake",
                audio_format="wav",
                poll_interval=0.0,
                poll_max=0.01,
            )
        assert exc_info.value.code == "TIMEOUT"
        assert "ASR polling timed out" in exc_info.value.message


class TestSeedSpeechAsrServiceLifecycle:
    """Tests for gateway close and resource cleanup (fix #2)."""

    @respx.mock
    async def test_close_closes_owned_gateway(self, asr_env: None) -> None:
        service = SeedSpeechAsrService()
        assert service._gateway is None
        assert service._owns_gateway is True

        with patch.object(SeedSpeechAsrHttpGateway, "close", new_callable=AsyncMock) as mock_close:
            await service.close()
            # No gateway created yet, so close should not be called.
            mock_close.assert_not_called()

    @respx.mock
    async def test_close_does_not_close_injected_gateway(self) -> None:
        gw = SeedSpeechAsrHttpGateway(
            api_key="sk-test",  # pragma: allowlist secret
            base_url=ASR_BASE,
            timeout=10.0,
            connect_timeout=5.0,
        )
        service = SeedSpeechAsrService(gateway=gw)
        assert service._owns_gateway is False

        with patch.object(gw, "close", new_callable=AsyncMock) as mock_close:
            await service.close()
            mock_close.assert_not_called()

    @respx.mock
    async def test_transcribe_closes_gateway_on_submit_error(self) -> None:
        gw = SeedSpeechAsrHttpGateway(
            api_key="sk-test",  # pragma: allowlist secret
            base_url=ASR_BASE,
            timeout=10.0,
            connect_timeout=5.0,
        )
        service = SeedSpeechAsrService(gateway=gw)

        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            side_effect=httpx.ConnectError("refused")
        )

        with patch.object(gw, "close", new_callable=AsyncMock) as mock_close:
            with pytest.raises(ProviderError):
                await service.transcribe(audio_bytes=b"fake", audio_format="wav")
            # Gateway was injected, so _safe_close should not close it.
            mock_close.assert_not_called()

    @respx.mock
    async def test_transcribe_closes_owned_gateway_on_submit_error(self, asr_env: None) -> None:
        service = SeedSpeechAsrService()

        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            side_effect=httpx.ConnectError("refused")
        )

        with patch.object(SeedSpeechAsrHttpGateway, "close", new_callable=AsyncMock) as mock_close:
            with pytest.raises(ProviderError):
                await service.transcribe(audio_bytes=b"fake", audio_format="wav")
            mock_close.assert_called_once()

    @respx.mock
    async def test_transcribe_closes_owned_gateway_on_query_error(self, asr_env: None) -> None:
        service = SeedSpeechAsrService()

        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            side_effect=httpx.ConnectError("refused")
        )

        with patch.object(SeedSpeechAsrHttpGateway, "close", new_callable=AsyncMock) as mock_close:
            with pytest.raises(ProviderError):
                await service.transcribe(
                    audio_bytes=b"fake", audio_format="wav", poll_interval=0.0, poll_max=1.0
                )
            mock_close.assert_called_once()

    @respx.mock
    async def test_transcribe_closes_owned_gateway_on_success(self, asr_env: None) -> None:
        service = SeedSpeechAsrService()

        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(200, json=_asr_result_body())
        )

        with patch.object(SeedSpeechAsrHttpGateway, "close", new_callable=AsyncMock) as mock_close:
            result, _ = await service.transcribe(
                audio_bytes=b"fake", audio_format="wav", poll_interval=0.0, poll_max=5.0
            )
            assert result.text == "hello world"
            await service.close()
            mock_close.assert_called_once()
