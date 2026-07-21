"""Contract tests for the Seed Audio adapter (full-scene audio generation).

Tests request building, reference mapping, response parsing, subtitle
extraction, and error propagation.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.seed_speech.client import SeedSpeechGateway
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService

SPEECH_BASE = "https://voice.ap-southeast-1.bytepluses.com"


@pytest.fixture
def service() -> SeedAudioService:
    """Create a SeedAudioService with a test gateway."""
    gateway = SeedSpeechGateway(
        api_key="sk-test-key",  # pragma: allowlist secret
        base_url=SPEECH_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )
    return SeedAudioService(gateway=gateway)


class TestSeedAudioRequestBuilding:
    """Tests for provider request construction."""

    def test_text_only_request(self) -> None:
        request = SeedAudioService.build_request(text_prompt="Hello world")
        assert request.model == "seed-audio-1.0"
        assert request.text_prompt == "Hello world"
        assert request.references is None

    def test_request_with_references(self) -> None:
        refs = [{"speaker": "voice_001"}]
        request = SeedAudioService.build_request(text_prompt="Hello", references=refs)
        assert request.references == refs

    def test_request_with_output_options(self) -> None:
        output = {"format": "mp3", "sample_rate": 44100}
        request = SeedAudioService.build_request(text_prompt="Hello", output=output)
        assert request.output == output

    def test_request_with_watermark(self) -> None:
        watermark = {"enable": True, "metadata": True}
        request = SeedAudioService.build_request(text_prompt="Hello", watermark=watermark)
        assert request.watermark == watermark


class TestSeedAudioReferenceMapping:
    """Tests for the build_references helper."""

    def test_speaker_reference(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=[{"kind": "speaker", "speaker_id": "voice_001"}],
            image_ref=None,
        )
        assert refs == [{"speaker": "voice_001"}]

    def test_url_audio_reference(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=[
                {
                    "kind": "url",
                    "url": "https://cdn.example.com/voice.wav",
                    "mime_type": "audio/wav",
                }
            ],
            image_ref=None,
        )
        assert refs[0]["audio_url"] == "https://cdn.example.com/voice.wav"
        assert refs[0]["mime_type"] == "audio/wav"

    def test_base64_audio_reference(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=[{"kind": "base64", "data": "aGVsbG8=", "mime_type": "audio/wav"}],
            image_ref=None,
        )
        assert refs[0]["audio_data"] == "aGVsbG8="
        assert refs[0]["mime_type"] == "audio/wav"

    def test_image_url_reference(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=None,
            image_ref={
                "kind": "url",
                "url": "https://cdn.example.com/scene.png",
                "mime_type": "image/png",
            },
        )
        assert refs[0]["image_url"] == "https://cdn.example.com/scene.png"
        assert refs[0]["mime_type"] == "image/png"

    def test_image_base64_reference(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=None,
            image_ref={"kind": "base64", "data": "aW1hZ2U=", "mime_type": "image/png"},
        )
        assert refs[0]["image_data"] == "aW1hZ2U="

    def test_multiple_audio_references(self) -> None:
        refs = SeedAudioService.build_references(
            audio_refs=[
                {"kind": "speaker", "speaker_id": "v1"},
                {"kind": "url", "url": "https://cdn.example.com/v2.wav"},
                {"kind": "base64", "data": "aGk="},
            ],
            image_ref=None,
        )
        assert len(refs) == 3

    def test_empty_inputs(self) -> None:
        refs = SeedAudioService.build_references(audio_refs=None, image_ref=None)
        assert refs == []


class TestSeedAudioResponseParsing:
    """Tests for provider response parsing."""

    @respx.mock
    async def test_success_with_base64_audio(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "audio": "aGVsbG8=",
                    "duration": 1.5,
                    "original_duration": 2.0,
                    "url": "https://cdn.example.com/audio.wav",
                },
                headers={"X-Tt-Logid": "log-1"},
            )
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        response, log_id = await service.generate(request)
        assert log_id == "log-1"
        assert response.code == 0
        assert response.audio == "aGVsbG8="
        assert response.duration == 1.5
        assert response.original_duration == 2.0
        assert response.url == "https://cdn.example.com/audio.wav"

    @respx.mock
    async def test_success_with_subtitle(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "audio": "aGVsbG8=",
                    "duration": 1.0,
                    "url": "https://cdn.example.com/audio.wav",
                    "subtitle": {
                        "utterances": [{"text": "Hello", "start": 0.0, "end": 0.5}],
                        "words": [{"text": "Hel", "start": 0.0, "end": 0.25}],
                    },
                },
            )
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        response, _ = await service.generate(request)
        subtitle = SeedAudioService.extract_subtitle(response)
        assert subtitle is not None
        assert len(subtitle.utterances) == 1
        assert len(subtitle.words) == 1

    @respx.mock
    async def test_success_without_subtitle(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "audio": "aGVsbG8=",
                    "duration": 1.0,
                },
            )
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        response, _ = await service.generate(request)
        assert SeedAudioService.extract_subtitle(response) is None

    @respx.mock
    async def test_request_id_passed_to_header(self, service: SeedAudioService) -> None:
        route = respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(200, json={"code": 0, "audio": "aGk="})
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        await service.generate(request, request_id="req-abc")
        assert route.calls.last.request.headers["X-Api-Request-Id"] == "req-abc"


class TestSeedAudioErrorPropagation:
    """Tests for error propagation through the Seed Audio adapter."""

    @respx.mock
    async def test_provider_error_raised(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            return_value=httpx.Response(
                400,
                json={"code": 1001, "message": "text_prompt is required"},
                headers={"X-Tt-Logid": "log-err"},
            )
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.http_status == 400
        assert exc_info.value.code == "1001"
        assert exc_info.value.request_id == "log-err"

    @respx.mock
    async def test_timeout_raises_ambiguous(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_connection_error_raises(self, service: SeedAudioService) -> None:
        respx.post(f"{SPEECH_BASE}/api/v3/tts/create").mock(
            side_effect=httpx.ConnectError("refused")
        )
        request = SeedAudioService.build_request(text_prompt="Hello")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.code == "CONNECTION_ERROR"
