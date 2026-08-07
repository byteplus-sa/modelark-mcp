"""Unit tests for Seedance 2.5 input model validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modelark_mcp.tools._seedance_shared import (
    SeedanceAudioInput,
    SeedanceImageInput,
    SeedanceVideoInput,
)
from modelark_mcp.tools.seedance_2_5_create_task import Seedance25CreateTaskInput
from modelark_mcp.tools.seedance_2_5_create_task_variations import (
    Seedance25VariationsInput,
)


class TestSeedance25CreateTaskInput:
    """Tests for Seedance25CreateTaskInput validators."""

    def test_text_only_accepted(self) -> None:
        inp = Seedance25CreateTaskInput(prompt="a cat walking")
        assert inp.prompt == "a cat walking"

    def test_duration_30_accepted(self) -> None:
        inp = Seedance25CreateTaskInput(prompt="test", duration=30)
        assert inp.duration == 30

    def test_duration_31_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", duration=31)

    def test_duration_auto_accepted(self) -> None:
        inp = Seedance25CreateTaskInput(prompt="test", duration=-1)
        assert inp.duration == -1

    def test_resolution_480p_accepted(self) -> None:
        inp = Seedance25CreateTaskInput(prompt="test", resolution="480p")
        assert inp.resolution == "480p"

    def test_resolution_720p_accepted(self) -> None:
        inp = Seedance25CreateTaskInput(prompt="test", resolution="720p")
        assert inp.resolution == "720p"

    def test_resolution_1080p_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", resolution="1080p")

    def test_resolution_4k_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", resolution="4k")

    def test_30_images_accepted(self) -> None:
        images = [
            SeedanceImageInput(kind="url", url=f"https://example.com/img{i}.jpg") for i in range(30)
        ]
        inp = Seedance25CreateTaskInput(prompt="test", images=images)
        assert len(inp.images) == 30

    def test_31_images_rejected(self) -> None:
        images = [
            SeedanceImageInput(kind="url", url=f"https://example.com/img{i}.jpg") for i in range(31)
        ]
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", images=images)

    def test_10_videos_accepted(self) -> None:
        videos = [SeedanceVideoInput(url=f"https://example.com/vid{i}.mp4") for i in range(10)]
        inp = Seedance25CreateTaskInput(prompt="test", videos=videos)
        assert len(inp.videos) == 10

    def test_11_videos_rejected(self) -> None:
        videos = [SeedanceVideoInput(url=f"https://example.com/vid{i}.mp4") for i in range(11)]
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", videos=videos)

    def test_10_audios_accepted(self) -> None:
        videos = [SeedanceVideoInput(url="https://example.com/vid.mp4")]
        audios = [
            SeedanceAudioInput(kind="url", url=f"https://example.com/aud{i}.mp3") for i in range(10)
        ]
        inp = Seedance25CreateTaskInput(prompt="test", videos=videos, audios=audios)
        assert len(inp.audios) == 10

    def test_11_audios_rejected(self) -> None:
        videos = [SeedanceVideoInput(url="https://example.com/vid.mp4")]
        audios = [
            SeedanceAudioInput(kind="url", url=f"https://example.com/aud{i}.mp3") for i in range(11)
        ]
        with pytest.raises(ValidationError):
            Seedance25CreateTaskInput(prompt="test", videos=videos, audios=audios)

    def test_audio_only_rejected(self) -> None:
        audios = [SeedanceAudioInput(kind="url", url="https://example.com/aud.mp3")]
        with pytest.raises(ValidationError, match="sole media input"):
            Seedance25CreateTaskInput(audios=audios)

    def test_no_prompt_no_media_rejected(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            Seedance25CreateTaskInput()


class TestSeedance25VariationsInput:
    """Tests for Seedance25VariationsInput validators."""

    def test_prompt_required_when_no_variation_prompts(self) -> None:
        """When media is provided but neither prompt nor variation_prompts, raises."""
        images = [SeedanceImageInput(kind="url", url="https://example.com/img.jpg")]
        with pytest.raises(ValidationError, match="Either prompt or variation_prompts"):
            Seedance25VariationsInput(variations=2, images=images)

    def test_variation_prompts_length_must_match(self) -> None:
        with pytest.raises(ValidationError, match="exactly 3"):
            Seedance25VariationsInput(
                variations=3,
                variation_prompts=["a", "b"],
            )

    def test_too_many_variations_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Seedance25VariationsInput(variations=6, prompt="test")

    def test_valid_variations(self) -> None:
        inp = Seedance25VariationsInput(
            variations=3,
            variation_prompts=["a cat", "a dog", "a bird"],
        )
        assert inp.variations == 3
        assert len(inp.variation_prompts) == 3

    def test_inherits_2_5_duration_limit(self) -> None:
        inp = Seedance25VariationsInput(prompt="test", variations=1, duration=30)
        assert inp.duration == 30

    def test_inherits_2_5_duration_rejection(self) -> None:
        with pytest.raises(ValidationError):
            Seedance25VariationsInput(prompt="test", variations=1, duration=31)
