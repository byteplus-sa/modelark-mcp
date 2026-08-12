"""Shared Seedance tool components.

Input types (``SeedanceImageInput``, ``SeedanceVideoInput``,
``SeedanceAudioInput``) and the ``execute_seedance_create`` helper used by
both Seedance 2.0 and 2.5 tool handlers.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.model_capabilities import VideoCapabilities
from modelark_mcp.domain.artifacts import MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import MediaSource
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedance import SeedanceService
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.runtime import billed_provider_slot, get_principal, get_runtime
from modelark_mcp.security.url_policy import validate_url
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._errors import provider_error_result


class SeedanceImageInput(MediaSource):
    """Image input with an optional role for Seedance."""

    MEDIA_CATEGORY: ClassVar[MediaType] = MediaType.IMAGE
    role: Literal["first_frame", "last_frame", "reference_image"] | None = Field(
        None,
        description="Role of this image: first_frame, last_frame, or reference_image. If omitted, provider default applies.",
    )


class SeedanceVideoInput(BaseModel):
    """Video reference input for Seedance."""

    kind: Literal["url"] = Field(
        "url",
        description="Media source kind. Always 'url' for video references.",
    )
    url: str = Field(..., description="HTTPS URL of the reference video.")
    role: Literal["reference_video"] = Field(
        "reference_video",
        description="Role of this input. Always 'reference_video'.",
    )

    @model_validator(mode="after")
    def validate_video_url(self) -> SeedanceVideoInput:
        validate_url(self.url)
        return self


class SeedanceAudioInput(MediaSource):
    """Audio reference input for Seedance."""

    MEDIA_CATEGORY: ClassVar[MediaType] = MediaType.AUDIO
    role: Literal["reference_audio"] = Field(
        "reference_audio",
        description="Role of this input. Always 'reference_audio'.",
    )


async def execute_seedance_create(
    input_model: Any,
    ctx: Context,
    caps: VideoCapabilities,
) -> tuple[str, str | None] | ToolResult:
    """Execute a Seedance task creation using the resolved capabilities.

    Shared by both 2.0 and 2.5 create handlers. Handles content building,
    request building, billing, retry, ownership recording, and logging.

    Args:
        input_model: The validated input model (SeedanceCreateTaskInput or
            Seedance25CreateTaskInput). Must have prompt, images, videos,
            audios, resolution, ratio, duration, omni_reference_task_type,
            generate_audio, watermark, return_last_frame,
            execution_expires_after, priority, safety_identifier fields.
        ctx: MCP Context.
        caps: Resolved VideoCapabilities for the target model.

    Returns:
        ``(task_id, request_id)`` on success, or a ``ToolResult`` on
        provider error.
    """
    await ctx.report_progress(progress=30, total=100)

    images_data = None
    videos_data = None
    audios_data = None

    if input_model.images:
        images_data = [img.model_dump() for img in input_model.images]
    if input_model.videos:
        videos_data = [vid.model_dump() for vid in input_model.videos]
    if input_model.audios:
        audios_data = [aud.model_dump() for aud in input_model.audios]

    content = SeedanceService.build_content(
        prompt=input_model.prompt,
        images=images_data,
        videos=videos_data,
        audios=audios_data,
    )

    request = SeedanceService.build_request(
        model=caps.model_id,
        content=content,
        resolution=input_model.resolution,
        ratio=input_model.ratio,
        duration=input_model.duration,
        generate_audio=input_model.generate_audio,
        watermark=input_model.watermark,
        return_last_frame=input_model.return_last_frame,
        execution_expires_after=input_model.execution_expires_after,
        priority=input_model.priority,
        safety_identifier=input_model.safety_identifier,
        omni_reference_task_type=input_model.omni_reference_task_type,
    )

    await ctx.report_progress(progress=50, total=100)

    estimated_cost = log_cost_estimate(product="video", variations=1, model_id=caps.model_id)

    service = SeedanceService()
    try:
        async with billed_provider_slot(
            ctx,
            provider="modelark",
            product="video",
            estimated_cost_usd=estimated_cost,
        ):
            task_id, request_id = await call_with_retry(lambda: service.create_task(request))
    except ProviderError as exc:
        await ctx.error(f"Seedance task creation failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await get_runtime(ctx).ownership_store.record("modelark", task_id, get_principal(ctx))

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedance_task_created",
        task_id=task_id,
        model=caps.model_id,
        request_id=request_id,
    )

    return task_id, request_id
