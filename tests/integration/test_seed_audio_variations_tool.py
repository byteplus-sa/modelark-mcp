"""Integration tests for the ``seed_audio_generate_variations`` tool."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import patch

import pytest

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.seed_speech.schemas import SeedAudioProviderResponse
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService
from modelark_mcp.test_utils import FakeContext
from modelark_mcp.tools.seed_audio_generate_variations import (
    SeedAudioVariationsInput,
    SeedAudioVariationsOutput,
    seed_audio_generate_variations,
)


def _patch_audio_by_prompt(
    monkeypatch: pytest.MonkeyPatch,
    responses_by_prompt: dict[str, dict[str, Any] | Exception],
) -> None:
    """Mock SeedAudioService.generate to return different results based on the prompt."""

    async def mock_generate(
        self: SeedAudioService,
        request: Any,
        *,
        request_id: str | None = None,
    ) -> tuple[SeedAudioProviderResponse, str | None]:
        response = responses_by_prompt.get(request.text_prompt)
        if isinstance(response, Exception):
            raise response
        return SeedAudioProviderResponse.model_validate(response), "log-test"

    monkeypatch.setattr(SeedAudioService, "generate", mock_generate)

    async def mock_close(self: SeedAudioService) -> None:
        pass

    monkeypatch.setattr(SeedAudioService, "close", mock_close)


class TestSeedAudioVariationsTool:
    """Integration tests for seed_audio_generate_variations."""

    async def test_three_variations_all_succeed(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio_b64 = base64.b64encode(b"fake-audio").decode()
        _patch_audio_by_prompt(
            monkeypatch,
            {
                "hello": {"code": 0, "audio": audio_b64, "duration": 1.0},
            },
        )

        with patch("modelark_mcp.server.get_artifact_store", return_value=temp_store):
            result = await seed_audio_generate_variations(
                SeedAudioVariationsInput(
                    text_prompt="hello",
                    variations=3,
                ),
                fake_ctx,
            )

        assert isinstance(result, SeedAudioVariationsOutput)
        assert result.summary.total == 3
        assert result.summary.succeeded == 3
        assert result.summary.failed == 0

    async def test_partial_failure(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        audio_b64 = base64.b64encode(b"fake").decode()
        _patch_audio_by_prompt(
            monkeypatch,
            {
                "good": {"code": 0, "audio": audio_b64, "duration": 1.0},
                "bad": ProviderError(
                    NormalizedProviderError(
                        provider="seed-speech",
                        operation="generate_audio",
                        http_status=400,
                        code="INVALID_PARAM",
                        message="bad",
                        retryable=False,
                    )
                ),
            },
        )

        with patch("modelark_mcp.server.get_artifact_store", return_value=temp_store):
            result = await seed_audio_generate_variations(
                SeedAudioVariationsInput(
                    variation_prompts=["good", "bad", "good"],
                    variations=3,
                ),
                fake_ctx,
            )

        assert result.summary.succeeded == 2
        assert result.summary.failed == 1
        assert result.summary.variations[1].error is not None

    async def test_no_prompt_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Either text_prompt or variation_prompts"):
            SeedAudioVariationsInput(variations=2)

    async def test_media_mixing_raises(self) -> None:
        from pydantic import ValidationError

        from modelark_mcp.domain.media import AudioReference, MediaSource, MediaSourceKind

        with pytest.raises(ValidationError, match="mutually exclusive"):
            SeedAudioVariationsInput(
                text_prompt="test",
                variations=1,
                audio_references=[AudioReference(kind="speaker", speaker_id="v1")],
                image_reference=MediaSource(kind=MediaSourceKind.url, url="https://x.com/i.png"),
            )
