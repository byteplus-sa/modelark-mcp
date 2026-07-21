"""Contract tests for the Seed Speech gateway.

Covers the same error paths as the ModelArk gateway tests but for the
Seed Speech host (``X-Api-Key`` auth, ``X-Tt-Logid`` diagnostic header).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from modelark_mcp.providers.seed_speech.client import SeedSpeechGateway

SPEECH_BASE = "https://voice.ap-southeast-1.bytepluses.com"


@pytest.fixture
def gateway() -> SeedSpeechGateway:
    """Create a Seed Speech gateway with test credentials."""
    return SeedSpeechGateway(
        api_key="sk-test-key",  # pragma: allowlist secret
        base_url=SPEECH_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )


class TestSeedSpeechGatewaySuccess:
    """Tests for successful Seed Speech API calls."""

    @respx.mock
    async def test_post_success(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "audio": "aGVsbG8=",
                    "duration": 1.5,
                    "original_duration": 1.5,
                    "url": "https://cdn.example.com/audio.wav",
                },
                headers={"X-Tt-Logid": "log-123"},
            )
        )
        response = await gateway.post(
            "/api/v3/tts/create", {"model": "seed-audio-1.0", "text_prompt": "hello"}
        )
        assert response.status_code == 200
        assert response.json()["audio"] == "aGVsbG8="

    @respx.mock
    async def test_x_api_key_header_set(self, gateway: SeedSpeechGateway) -> None:
        route = respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(200, json={})
        )
        await gateway.post("/api/v3/tts/create", {})
        assert route.calls.last.request.headers["X-Api-Key"] == "sk-test-key"

    @respx.mock
    async def test_request_id_header_passed(self, gateway: SeedSpeechGateway) -> None:
        route = respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(200, json={})
        )
        await gateway.post("/api/v3/tts/create", {}, request_id="req-abc")
        assert route.calls.last.request.headers["X-Api-Request-Id"] == "req-abc"

    @respx.mock
    async def test_extract_log_id(self, gateway: SeedSpeechGateway) -> None:
        response = httpx.Response(200, json={}, headers={"X-Tt-Logid": "log-abc"})
        assert SeedSpeechGateway.extract_log_id(response) == "log-abc"

    @respx.mock
    async def test_extract_log_id_lowercase(self, gateway: SeedSpeechGateway) -> None:
        response = httpx.Response(200, json={}, headers={"x-tt-logid": "log-xyz"})
        assert SeedSpeechGateway.extract_log_id(response) == "log-xyz"

    @respx.mock
    async def test_extract_log_id_missing(self, gateway: SeedSpeechGateway) -> None:
        response = httpx.Response(200, json={})
        assert SeedSpeechGateway.extract_log_id(response) is None


class TestSeedSpeechGatewayErrors:
    """Tests for Seed Speech error normalization."""

    @respx.mock
    async def test_400_validation_error(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                400,
                json={"code": 1001, "message": "text_prompt is required"},
                headers={"X-Tt-Logid": "log-400"},
            )
        )
        response = await gateway.post("/api/v3/tts/create", {})
        error = SeedSpeechGateway.normalize_error(response, "generate_audio")
        assert error.provider == "seed-speech"
        assert error.http_status == 400
        assert error.code == "1001"
        assert "text_prompt is required" in error.message
        assert error.request_id == "log-400"
        assert not error.retryable

    @respx.mock
    async def test_401_access_error(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                401,
                json={"code": 1002, "message": "invalid API key"},
            )
        )
        response = await gateway.post("/api/v3/tts/create", {})
        error = SeedSpeechGateway.normalize_error(response, "generate_audio")
        assert error.http_status == 401
        assert not error.retryable

    @respx.mock
    async def test_429_rate_limit(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                429,
                json={"code": 1003, "message": "rate limited"},
            )
        )
        response = await gateway.post("/api/v3/tts/create", {})
        error = SeedSpeechGateway.normalize_error(response, "generate_audio")
        assert error.http_status == 429
        # Seed Audio treats only 5xx as retryable per the plan.
        assert not error.retryable

    @respx.mock
    async def test_500_server_error(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                500,
                json={"code": 5000, "message": "internal error"},
            )
        )
        response = await gateway.post("/api/v3/tts/create", {})
        error = SeedSpeechGateway.normalize_error(response, "generate_audio")
        assert error.http_status == 500
        assert error.retryable

    @respx.mock
    async def test_malformed_json_body(self, gateway: SeedSpeechGateway) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(500, content=b"not json")
        )
        response = await gateway.post("/api/v3/tts/create", {})
        error = SeedSpeechGateway.normalize_error(response, "generate_audio")
        assert "not json" in error.message

    def test_normalize_timeout(self) -> None:
        error = SeedSpeechGateway.normalize_timeout("generate_audio")
        assert error.code == "TIMEOUT"
        assert error.ambiguous_completion is True
        assert not error.retryable
        assert "generate_audio" in error.message
        assert "may have succeeded" in error.message

    def test_normalize_connection_error(self) -> None:
        exc = httpx.ConnectError("connection refused")
        error = SeedSpeechGateway.normalize_connection_error("generate_audio", exc)
        assert error.code == "CONNECTION_ERROR"
        assert error.retryable
        assert "connection refused" in error.message
