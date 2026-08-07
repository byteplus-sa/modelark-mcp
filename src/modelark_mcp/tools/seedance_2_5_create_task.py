"""``seedance_2_5_create_task`` tool — create an asynchronous Seedance 2.5 video task.

Seedance 2.5 supports up to 30-second video generation, 50 multimodal
references (30 images, 10 videos, 10 audio), 480p/720p resolution, and
timestamp-level prompt control for editing.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import ModelFamily, get_capability_registry
from modelark_mcp.tools._seedance_shared import (
    SeedanceAudioInput,
    SeedanceImageInput,
    SeedanceVideoInput,
    execute_seedance_create,
)


class Seedance25CreateTaskInput(BaseModel):
    """Input model for ``seedance_2_5_create_task``."""

    prompt: str | None = Field(
        None,
        min_length=1,
        max_length=32000,
        description="Text prompt describing the video to generate (up to 32,000 characters). Optional when media inputs are provided.",
    )
    images: list[SeedanceImageInput] | None = Field(
        None,
        max_length=30,
        description="Reference images with optional roles (first_frame, last_frame, reference_image). Max 30 for Seedance 2.5.",
    )
    videos: list[SeedanceVideoInput] | None = Field(
        None,
        max_length=10,
        description="Reference videos. Max 10 for Seedance 2.5.",
    )
    audios: list[SeedanceAudioInput] | None = Field(
        None,
        max_length=10,
        description="Reference audio for audio-driven generation. Max 10 for Seedance 2.5. Cannot be the sole media input.",
    )
    model: str | None = Field(
        None,
        description="Model ID. Defaults to 'dreamina-seedance-2-5-260628'. Omit to use the default.",
    )
    resolution: Literal["480p", "720p"] | None = Field(
        None,
        description="Output video resolution. Seedance 2.5 supports 480p and 720p.",
    )
    ratio: str | None = Field(
        None,
        description="Output aspect ratio (e.g. '16:9', '9:16'). Must be supported by the selected model.",
    )
    duration: int | None = Field(
        None,
        ge=-1,
        le=30,
        description="Video duration in seconds (-1 for auto). Max 30 for Seedance 2.5.",
    )
    generate_audio: bool | None = Field(
        None, description="Whether to generate an audio track for the video."
    )
    watermark: bool | None = Field(
        None, description="Whether to apply an AIGC watermark to the video."
    )
    return_last_frame: bool | None = Field(
        None, description="Whether to return the last frame as a separate image output."
    )
    execution_expires_after: int | None = Field(
        None,
        ge=3600,
        le=259200,
        description="Maximum execution time in seconds before the task expires (3600-259200, i.e. 1 hour to 3 days).",
    )
    priority: int | None = Field(
        None,
        ge=0,
        le=9,
        description="Task priority (0-9). Higher values may incur additional cost.",
    )
    safety_identifier: str | None = Field(
        None,
        max_length=64,
        description="Optional identifier for content safety tracking (max 64 characters).",
    )

    @model_validator(mode="after")
    def validate_media_required(self) -> Seedance25CreateTaskInput:
        """Audio cannot be the sole media input; text-only is allowed."""
        has_images = bool(self.images)
        has_videos = bool(self.videos)
        has_audios = bool(self.audios)
        has_prompt = bool(self.prompt) or bool(getattr(self, "variation_prompts", None))

        if not has_images and not has_videos:
            if has_audios:
                raise ValueError(
                    "Audio references cannot be the sole media input. "
                    "At least one image or video is required."
                )
            if not has_prompt:
                raise ValueError("At least one of prompt, images, or videos is required.")
        return self

    @model_validator(mode="after")
    def validate_reference_counts(self) -> Seedance25CreateTaskInput:
        """Enforce reference count limits per Seedance 2.5 specs."""
        if self.images and len(self.images) > 30:
            raise ValueError(f"Too many reference images: {len(self.images)}. Maximum is 30.")
        if self.videos and len(self.videos) > 10:
            raise ValueError(f"Too many reference videos: {len(self.videos)}. Maximum is 10.")
        if self.audios and len(self.audios) > 10:
            raise ValueError(f"Too many reference audios: {len(self.audios)}. Maximum is 10.")
        return self


class Seedance25CreateTaskOutput(BaseModel):
    """Output model for ``seedance_2_5_create_task``."""

    task_id: str = Field(..., description="Provider task ID for polling and management.")
    status: Literal["queued"] = Field(
        "queued", description="Initial task status. Poll with seedance_get_task for updates."
    )
    recommended_poll_after_ms: int = Field(
        ..., description="Suggested delay in milliseconds before first poll."
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


async def seedance_2_5_create_task(
    input: Seedance25CreateTaskInput, ctx: Context
) -> Seedance25CreateTaskOutput | ToolResult:
    """Create an asynchronous Seedance 2.5 video generation task.

    Accepts text, image, video, and audio references as content input.
    Supports up to 30-second video generation, 50 multimodal references
    (30 images, 10 videos, 10 audio), and 480p/720p resolution.
    The task runs asynchronously on the provider — use
    ``seedance_get_task`` to poll for completion. Returns the task ID
    and a recommended polling interval.
    """
    await ctx.info("Creating Seedance 2.5 video generation task")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError(
            "BYTEPLUS_MODELARK_API_KEY is not configured. Set it in .env to enable Seedance tools."
        )

    registry = get_capability_registry()

    if input.model:
        caps = registry.get_video_capabilities(input.model)
        if caps.family is not ModelFamily.SEEDANCE_2_5:
            raise ValueError(
                f"Model '{input.model}' is not a Seedance 2.5 model. "
                f"Use seedance_create_task for Seedance 2.0 models."
            )
    else:
        video_models = registry.list_video_models()
        seedance_2_5_ids = [
            mid
            for mid in video_models
            if registry.get_video_capabilities(mid).family is ModelFamily.SEEDANCE_2_5
        ]
        if not seedance_2_5_ids:
            raise ValueError(
                "No Seedance 2.5 model is configured. Set SEEDANCE_MODEL_BINDINGS "
                'to include a {"model_id": "dreamina-seedance-2-5-260628", "family": "seedance_2_5"} binding.'
            )
        caps = registry.get_video_capabilities(seedance_2_5_ids[0])

    registry.validate_resolution(caps.model_id, input.resolution)
    registry.validate_duration(caps.model_id, input.duration)

    if input.priority is not None:
        lo, hi = caps.priority_range
        if input.priority < lo or input.priority > hi:
            raise ValueError(
                f"Priority {input.priority} is outside the supported range "
                f"[{lo}, {hi}] for model '{caps.model_id}'."
            )

    if input.execution_expires_after is not None:
        lo, hi = caps.execution_expires_after_range
        if input.execution_expires_after < lo or input.execution_expires_after > hi:
            raise ValueError(
                f"execution_expires_after {input.execution_expires_after} is "
                f"outside the supported range [{lo}, {hi}] for model "
                f"'{caps.model_id}'."
            )

    result = await execute_seedance_create(input, ctx, caps)
    if isinstance(result, ToolResult):
        return result
    task_id, _ = result
    return Seedance25CreateTaskOutput(
        task_id=task_id,
        status="queued",
        recommended_poll_after_ms=5000,
    )
