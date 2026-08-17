"""Unit tests for tool input validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modelark_mcp.domain.media import AudioReference, MediaSource, MediaSourceKind
from modelark_mcp.tools.seed_audio_generate import SeedAudioGenerateInput
from modelark_mcp.tools.seedance_cancel_or_delete_task import (
    SeedanceCancelOrDeleteInput,
)
from modelark_mcp.tools.seedance_create_task import SeedanceCreateTaskInput
from modelark_mcp.tools.seedance_create_task_variations import SeedanceVariationsInput


class TestSeedAudioGenerateInput:
    """Tests for Seed Audio tool input validation."""

    def test_text_only_valid(self) -> None:
        inp = SeedAudioGenerateInput(text_prompt="Hello world")
        assert inp.text_prompt == "Hello world"
        assert inp.audio_references == []
        assert inp.image_reference is None

    def test_empty_prompt_raises(self) -> None:
        with pytest.raises(ValidationError):
            SeedAudioGenerateInput(text_prompt="")

    def test_prompt_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            SeedAudioGenerateInput(text_prompt="x" * 3001)

    def test_too_many_audio_references_raises(self) -> None:
        refs = [AudioReference(kind="speaker", speaker_id=f"v{i}") for i in range(4)]
        with pytest.raises(ValidationError):
            SeedAudioGenerateInput(text_prompt="test", audio_references=refs)

    def test_audio_and_image_mixing_raises(self) -> None:
        with pytest.raises(ValidationError, match="mutually exclusive"):
            SeedAudioGenerateInput(
                text_prompt="test",
                audio_references=[AudioReference(kind="speaker", speaker_id="v1")],
                image_reference=MediaSource(
                    kind=MediaSourceKind.url, url="https://example.com/img.png"
                ),
            )


class TestSeedanceCreateTaskInput:
    """Tests for Seedance create task input validation."""

    def test_with_images_valid(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceImageInput

        inp = SeedanceCreateTaskInput(
            prompt="A cat",
            images=[SeedanceImageInput(kind="url", url="https://example.com/cat.png")],
        )
        assert inp.prompt == "A cat"
        assert len(inp.images or []) == 1

    def test_with_videos_valid(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceCreateTaskInput(
            prompt="A dog",
            videos=[SeedanceVideoInput(url="https://example.com/dog.mp4")],
        )
        assert len(inp.videos or []) == 1

    def test_text_only_valid(self) -> None:
        inp = SeedanceCreateTaskInput(prompt="Just text")
        assert inp.prompt == "Just text"
        assert inp.images is None
        assert inp.videos is None
        assert inp.audios is None

    def test_empty_request_raises(self) -> None:
        with pytest.raises(ValidationError, match="At least one of prompt"):
            SeedanceCreateTaskInput()

    def test_prompt_with_video_and_audio_valid(self) -> None:
        from modelark_mcp.tools.seedance_create_task import (
            SeedanceAudioInput,
            SeedanceVideoInput,
        )

        inp = SeedanceCreateTaskInput(
            prompt="A dancer moving to music",
            videos=[SeedanceVideoInput(url="https://example.com/dance.mp4")],
            audios=[SeedanceAudioInput(kind="url", url="https://example.com/song.wav")],
        )
        assert inp.prompt == "A dancer moving to music"
        assert inp.images is None
        assert len(inp.videos or []) == 1
        assert len(inp.audios or []) == 1

    def test_audio_only_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceAudioInput

        with pytest.raises(ValidationError, match="cannot be the sole media input"):
            SeedanceCreateTaskInput(
                audios=[SeedanceAudioInput(kind="url", url="https://example.com/a.wav")]
            )

    def test_audio_input_rejects_image_mime(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceAudioInput

        with pytest.raises(ValidationError, match="Audio MIME type"):
            SeedanceAudioInput(kind="base64", data="aGVsbG8=", mime_type="image/png")

    def test_too_many_images_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceImageInput

        images = [
            SeedanceImageInput(kind="url", url=f"https://example.com/img{i}.png") for i in range(10)
        ]
        with pytest.raises(ValidationError, match="Too many reference images"):
            SeedanceCreateTaskInput(images=images)

    def test_too_many_videos_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        videos = [SeedanceVideoInput(url=f"https://example.com/v{i}.mp4") for i in range(4)]
        with pytest.raises(ValidationError, match="Too many reference videos"):
            SeedanceCreateTaskInput(videos=videos)

    def test_duration_out_of_range_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        with pytest.raises(ValidationError):
            SeedanceCreateTaskInput(
                videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
                duration=20,
            )

    def test_empty_prompt_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        with pytest.raises(ValidationError):
            SeedanceCreateTaskInput(
                prompt="",
                videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            )

    def test_prompt_at_max_length_valid(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceCreateTaskInput(
            prompt="x" * 32000,
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
        )
        assert len(inp.prompt or "") == 32000

    def test_prompt_too_long_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        with pytest.raises(ValidationError):
            SeedanceCreateTaskInput(
                prompt="x" * 32001,
                videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            )

    def test_ratio_stripped_for_extend_video(self) -> None:
        """Ratio is stripped for extend_video to prevent InvalidParameter.TaskTypeConstraint."""
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceCreateTaskInput(
            prompt="extend this video",
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            omni_reference_task_type="extend_video",
            ratio="16:9",
        )
        assert inp.ratio is None

    def test_ratio_preserved_for_edit_video(self) -> None:
        """Ratio is not stripped for edit_video."""
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceCreateTaskInput(
            prompt="edit this video",
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            omni_reference_task_type="edit_video",
            ratio="16:9",
        )
        assert inp.ratio == "16:9"

    def test_ratio_preserved_for_auto_task_type(self) -> None:
        """Ratio is not stripped when omni_reference_task_type is omitted."""
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceCreateTaskInput(
            prompt="generate a video",
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            ratio="16:9",
        )
        assert inp.ratio == "16:9"


class TestSeedanceCancelOrDeleteInput:
    """Tests for Seedance cancel/delete input validation."""

    def test_cancel_queued_valid(self) -> None:
        inp = SeedanceCancelOrDeleteInput(
            task_id="task-123", mode="cancel", expected_status="queued"
        )
        assert inp.mode == "cancel"

    def test_delete_succeeded_valid(self) -> None:
        inp = SeedanceCancelOrDeleteInput(
            task_id="task-123", mode="delete", expected_status="succeeded"
        )
        assert inp.mode == "delete"

    def test_cancel_succeeded_raises(self) -> None:
        with pytest.raises(ValidationError, match="Cancel mode requires"):
            SeedanceCancelOrDeleteInput(
                task_id="task-123", mode="cancel", expected_status="succeeded"
            )

    def test_delete_queued_raises(self) -> None:
        with pytest.raises(ValidationError, match="Delete mode requires"):
            SeedanceCancelOrDeleteInput(task_id="task-123", mode="delete", expected_status="queued")


class TestSeedanceVariationsInput:
    """Tests for Seedance variations input prompt-length validation."""

    def test_variation_prompt_at_max_length_valid(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceVariationsInput(
            variation_prompts=["x" * 32000],
            variations=1,
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
        )
        assert len(inp.variation_prompts[0]) == 32000

    def test_variation_prompt_too_long_raises(self) -> None:
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        with pytest.raises(ValidationError):
            SeedanceVariationsInput(
                variation_prompts=["x" * 32001],
                variations=1,
                videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            )

    def test_inherits_ratio_stripping_for_extend_video(self) -> None:
        """Variations input inherits ratio stripping from base model."""
        from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput

        inp = SeedanceVariationsInput(
            variations=2,
            variation_prompts=["extend clip a", "extend clip b"],
            videos=[SeedanceVideoInput(url="https://example.com/v.mp4")],
            omni_reference_task_type="extend_video",
            ratio="9:16",
        )
        assert inp.ratio is None
