"""Integration tests for the ``seed_audio_generate`` tool handler.

Exercises the full path: input validation → provider call (mocked) →
artifact persistence → structured output.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService
from modelark_mcp.tools.seed_audio_generate import (
    SeedAudioGenerateInput,
    SeedAudioGenerateOutput,
    seed_audio_generate,
)
from tests.fixtures.fake_context import FakeContext

SPEECH_BASE = "https://voice.test.example.com"


def _patch_audio_service(monkeypatch: pytest.MonkeyPatch, response_data: dict[str, Any]) -> None:
    """Patch SeedAudioService.generate to return a fixed response."""

    async def mock_generate(
        self: SeedAudioService,
        request: Any,
        *,
        request_id: str | None = None,
    ) -> tuple[Any, str | None]:
        from modelark_mcp.providers.seed_speech.schemas import (
            SeedAudioProviderResponse,
        )

        response = SeedAudioProviderResponse.model_validate(response_data)
        return response, "log-test-123"

    monkeypatch.setattr(SeedAudioService, "generate", mock_generate)


class TestSeedAudioGenerateTool:
    """Full-path integration tests for seed_audio_generate."""

    async def test_text_only_generation_with_persistence(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio_b64 = base64.b64encode(b"fake audio data").decode()
        _patch_audio_service(
            monkeypatch,
            {
                "code": 0,
                "message": "success",
                "audio": audio_b64,
                "duration": 2.5,
                "original_duration": 3.0,
                "url": "https://example.com/audio.wav",
            },
        )

        with patch("modelark_mcp.artifacts.registry.get_artifact_store", return_value=temp_store):
            result = await seed_audio_generate(
                SeedAudioGenerateInput(text_prompt="Hello world"), fake_ctx
            )

        assert isinstance(result, SeedAudioGenerateOutput)
        assert result.provider == "byteplus-seed-speech"
        assert result.model == "seed-audio-1.0"
        assert result.duration_seconds == 2.5
        assert result.billing_duration_seconds == 3.0
        assert result.provider_log_id == "log-test-123"
        assert result.artifact.id != "provider-url"
        assert result.artifact.uri.startswith("seed-media://artifacts/")
        assert result.artifact.media_type == "audio"

        # Verify artifact was actually stored.
        stored = await temp_store.get(result.artifact.id)
        assert stored.data == b"fake audio data"
        assert stored.mime_type == "audio/wav"

    async def test_url_only_no_persistence(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_audio_service(
            monkeypatch,
            {
                "code": 0,
                "message": "success",
                "audio": None,
                "duration": 1.5,
                "original_duration": 2.0,
                "url": "https://example.com/audio.wav",
            },
        )

        with patch("modelark_mcp.artifacts.registry.get_artifact_store", return_value=temp_store):
            result = await seed_audio_generate(
                SeedAudioGenerateInput(text_prompt="Hello", persist=True), fake_ctx
            )

        # No base64 audio → falls back to provider URL ref.
        assert result.artifact.id == "provider-url"
        assert result.artifact.uri == "https://example.com/audio.wav"

    async def test_progress_reporting(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio_b64 = base64.b64encode(b"hi").decode()
        _patch_audio_service(
            monkeypatch,
            {"code": 0, "audio": audio_b64, "duration": 1.0, "original_duration": 1.0},
        )

        with patch("modelark_mcp.artifacts.registry.get_artifact_store", return_value=temp_store):
            await seed_audio_generate(SeedAudioGenerateInput(text_prompt="Hi"), fake_ctx)

        # Should have reported progress at 10, 30, 50, 80, 100.
        progresses = [p for p, _ in fake_ctx.progress_reports]
        assert 10 in progresses
        assert 30 in progresses
        assert 50 in progresses
        assert 80 in progresses
        assert 100 in progresses

    async def test_provider_error_propagates(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from modelark_mcp.domain.errors import NormalizedProviderError

        async def mock_generate(
            self: SeedAudioService,
            request: Any,
            *,
            request_id: str | None = None,
        ) -> tuple[Any, str | None]:
            raise ProviderError(
                NormalizedProviderError(
                    provider="seed-speech",
                    operation="generate_audio",
                    http_status=400,
                    code="INVALID_PARAM",
                    message="text too long",
                    retryable=False,
                )
            )

        monkeypatch.setattr(SeedAudioService, "generate", mock_generate)

        result = await seed_audio_generate(SeedAudioGenerateInput(text_prompt="test"), fake_ctx)
        assert isinstance(result, ToolResult)
        assert result.is_error
        assert result.structured_content is None
        text = result.content[0].text
        assert "seed-speech generate_audio failed" in text
        assert "code=INVALID_PARAM" in text
