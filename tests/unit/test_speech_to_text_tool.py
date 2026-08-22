"""Unit tests for the ``speech_to_text`` tool handler.

Covers the Base64 happy path through the Seed Speech ASR submit/query flow,
the exactly-one-source validator, the stdio gate and size cap for local
files, the BytePlus-only trusted-host policy for URLs, schema descriptions
on ``audio``/``options``, and request-ID reuse across retries.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp.tools import ToolResult

from modelark_mcp.config.env import get_settings
from modelark_mcp.runtime import close_runtime_services, create_runtime_services
from modelark_mcp.tools.speech_to_text import (
    _STT_MAX_BYTES,
    AsrAudioInput,
    SpeechToTextInput,
    SpeechToTextOutput,
    speech_to_text,
)
from tests.fixtures.fake_context import FakeContext

ASR_BASE = "https://voice.test.example.com"


def _asr_result_body() -> dict[str, object]:
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


@pytest.fixture
def stt_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTEPLUS_SEED_SPEECH_API_KEY", "sk-test-stt")
    monkeypatch.setenv("SEED_SPEECH_ASR_BASE_URL", ASR_BASE)
    monkeypatch.setenv("SEED_SPEECH_ASR_POLL_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("SEED_SPEECH_ASR_POLL_MAX_SECONDS", "10")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / ".artifacts"))
    monkeypatch.setenv("ARTIFACT_BACKEND", "filesystem")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def stt_ctx(stt_env: None) -> AsyncIterator[FakeContext]:
    runtime = await create_runtime_services(get_settings())
    try:
        yield FakeContext(lifespan_context={"runtime": runtime})
    finally:
        await close_runtime_services(runtime)


class TestSpeechToTextHappyPath:
    @respx.mock
    async def test_base64_transcribes_to_output(self, stt_ctx: FakeContext) -> None:
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit").mock(
            return_value=httpx.Response(200, json={})
        )
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                200,
                json=_asr_result_body(),
                headers={"x-api-status-code": "20000000"},
            )
        )

        result = await speech_to_text(
            SpeechToTextInput(
                audio=AsrAudioInput(
                    audio_data=base64.b64encode(b"fake wav payload").decode(),
                    audio_format="wav",
                )
            ),
            stt_ctx,
        )

        assert isinstance(result, SpeechToTextOutput)
        assert result.result.text == "hello world"
        assert result.result.duration_ms == 1500
        assert len(result.result.utterances) == 1
        assert result.result.utterances[0].words[0].text == "hello"
        assert result.log_id is None

    @respx.mock
    async def test_retry_resubmits_the_same_request_id(self, stt_ctx: FakeContext) -> None:
        submit_route = respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/submit")
        submit_route.side_effect = [
            httpx.Response(429, json={"code": "RATE_LIMITED", "message": "slow down"}),
            httpx.Response(200, json={}),
        ]
        respx.post(f"{ASR_BASE}/api/v3/auc/bigmodel/query").mock(
            return_value=httpx.Response(
                200,
                json=_asr_result_body(),
                headers={"x-api-status-code": "20000000"},
            )
        )

        result = await speech_to_text(
            SpeechToTextInput(
                audio=AsrAudioInput(
                    audio_data=base64.b64encode(b"fake wav payload").decode(),
                    audio_format="wav",
                )
            ),
            stt_ctx,
        )

        assert isinstance(result, SpeechToTextOutput)
        assert len(submit_route.calls) == 2
        first_request_id = submit_route.calls[0].request.headers["X-Api-Request-Id"]
        second_request_id = submit_route.calls[1].request.headers["X-Api-Request-Id"]
        assert first_request_id == second_request_id


class TestSpeechToTextAudioResolution:
    async def test_url_to_untrusted_host_is_rejected(self, stt_ctx: FakeContext) -> None:
        result = await speech_to_text(
            SpeechToTextInput(
                audio=AsrAudioInput(
                    audio_url="https://evil.example.com/audio.wav",
                    audio_format="wav",
                )
            ),
            stt_ctx,
        )

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert "Invalid audio input" in result.content[0].text

    async def test_file_path_rejected_on_http_transport(
        self,
        stt_ctx: FakeContext,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        get_settings.cache_clear()
        sample = tmp_path / "clip.wav"
        sample.write_bytes(b"fake")
        try:
            result = await speech_to_text(
                SpeechToTextInput(
                    audio=AsrAudioInput(audio_file_path=str(sample), audio_format="wav")
                ),
                stt_ctx,
            )
        finally:
            get_settings.cache_clear()

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert "audio_file_path is only supported in stdio transport mode" in result.content[0].text

    async def test_file_path_rejected_when_over_size_limit(
        self,
        stt_ctx: FakeContext,
        tmp_path: Path,
    ) -> None:
        sample = tmp_path / "huge.wav"
        with sample.open("wb") as file_obj:
            file_obj.truncate(_STT_MAX_BYTES + 1)

        result = await speech_to_text(
            SpeechToTextInput(audio=AsrAudioInput(audio_file_path=str(sample), audio_format="wav")),
            stt_ctx,
        )

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert "exceeds limit" in result.content[0].text


class TestSpeechToTextInputValidation:
    def test_requires_exactly_one_source(self) -> None:
        with pytest.raises(ValueError, match="Provide exactly one of"):
            AsrAudioInput(
                audio_url="https://example.com/a.wav",
                audio_data="aGVsbG8=",
                audio_format="wav",
            )

    def test_requires_at_least_one_source(self) -> None:
        with pytest.raises(ValueError, match="Provide exactly one of"):
            AsrAudioInput(audio_format="wav")

    def test_audio_field_has_description(self) -> None:
        assert SpeechToTextInput.model_fields["audio"].description is not None
        assert len(SpeechToTextInput.model_fields["audio"].description or "") > 0

    def test_options_field_has_description(self) -> None:
        assert SpeechToTextInput.model_fields["options"].description is not None
        assert len(SpeechToTextInput.model_fields["options"].description or "") > 0
