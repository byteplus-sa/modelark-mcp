"""``seedance_create_task`` tool — create an asynchronous Seedance video task.

The capability registry validates whether the selected model supports a
field or resolution. Pydantic cross-field validators enforce Seedance 2.0
duration bounds, reference roles, media counts, and the rule that audio
cannot be the sole media input.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import get_capability_registry
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import MediaSource
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedance import SeedanceService

# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------


class SeedanceImageInput(MediaSource):
    """Image input with an optional role for Seedance."""

    role: Literal["first_frame", "last_frame", "reference_image"] | None = None


class SeedanceVideoInput(BaseModel):
    """Video reference input for Seedance."""

    kind: Literal["url"] = "url"
    url: str
    role: Literal["reference_video"] = "reference_video"


class SeedanceAudioInput(MediaSource):
    """Audio reference input for Seedance."""

    role: Literal["reference_audio"] = "reference_audio"


class SeedanceCreateTaskInput(BaseModel):
    """Input model for ``seedance_create_task``."""

    prompt: str | None = None
    images: list[SeedanceImageInput] | None = None
    videos: list[SeedanceVideoInput] | None = None
    audios: list[SeedanceAudioInput] | None = None
    model: str | None = None
    resolution: Literal["480p", "720p", "1080p", "4k"] | None = None
    ratio: str | None = None
    duration: int | None = Field(None, ge=-1, le=15)
    generate_audio: bool | None = None
    watermark: bool | None = None
    return_last_frame: bool | None = None
    execution_expires_after: int | None = Field(None, ge=3600, le=259200)
    priority: int | None = Field(None, ge=0, le=9)
    safety_identifier: str | None = Field(None, max_length=64)

    @model_validator(mode="after")
    def validate_media_required(self) -> SeedanceCreateTaskInput:
        """Audio cannot be the sole media input; at least one image or video is required."""
        has_images = bool(self.images)
        has_videos = bool(self.videos)
        has_audios = bool(self.audios)

        if not has_images and not has_videos:
            if has_audios:
                raise ValueError(
                    "Audio references cannot be the sole media input. "
                    "At least one image or video is required."
                )
            raise ValueError(
                "At least one media input (image, video) is required. "
                "Prompt-only text generation is not sufficient."
            )
        return self

    @model_validator(mode="after")
    def validate_reference_counts(self) -> SeedanceCreateTaskInput:
        """Enforce reference count limits per Seedance 2.0 docs."""
        if self.images and len(self.images) > 9:
            raise ValueError(f"Too many reference images: {len(self.images)}. Maximum is 9.")
        if self.videos and len(self.videos) > 3:
            raise ValueError(f"Too many reference videos: {len(self.videos)}. Maximum is 3.")
        if self.audios and len(self.audios) > 3:
            raise ValueError(f"Too many reference audios: {len(self.audios)}. Maximum is 3.")
        return self


class SeedanceCreateTaskOutput(BaseModel):
    """Output model for ``seedance_create_task``."""

    task_id: str
    status: Literal["queued"] = "queued"
    recommended_poll_after_ms: int


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def seedance_create_task(
    input: SeedanceCreateTaskInput, ctx: Context
) -> SeedanceCreateTaskOutput:
    """Create an asynchronous Seedance video generation task.

    Accepts text, image, video, and audio references as content input.
    The task runs asynchronously on the provider — use
    ``seedance_get_task`` to poll for completion. Returns the task ID
    and a recommended polling interval.
    """
    await ctx.info("Creating Seedance video generation task")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError(
            "BYTEPLUS_MODELARK_API_KEY is not configured. Set it in .env to enable Seedance tools."
        )

    registry = get_capability_registry()
    caps = registry.get_video_capabilities(input.model)

    # Validate model-specific capabilities.
    registry.validate_resolution(input.model, input.resolution)
    registry.validate_duration(input.model, input.duration)

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

    await ctx.report_progress(progress=30, total=100)

    # Build the provider content array.
    images_data = None
    videos_data = None
    audios_data = None

    if input.images:
        images_data = [img.model_dump() for img in input.images]
    if input.videos:
        videos_data = [vid.model_dump() for vid in input.videos]
    if input.audios:
        audios_data = [aud.model_dump() for aud in input.audios]

    content = SeedanceService.build_content(
        prompt=input.prompt,
        images=images_data,
        videos=videos_data,
        audios=audios_data,
    )

    request = SeedanceService.build_request(
        model=caps.model_id,
        content=content,
        resolution=input.resolution,
        ratio=input.ratio,
        duration=input.duration,
        generate_audio=input.generate_audio,
        watermark=input.watermark,
        return_last_frame=input.return_last_frame,
        execution_expires_after=input.execution_expires_after,
        priority=input.priority,
        safety_identifier=input.safety_identifier,
    )

    await ctx.report_progress(progress=50, total=100)

    service = SeedanceService()
    try:
        task_id, request_id = await service.create_task(request)
    except ProviderError as exc:
        await ctx.error(f"Seedance task creation failed: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedance_task_created",
        task_id=task_id,
        model=caps.model_id,
        request_id=request_id,
    )

    # Recommend polling after ~5 seconds for the first check.
    return SeedanceCreateTaskOutput(
        task_id=task_id,
        status="queued",
        recommended_poll_after_ms=5000,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
