"""``seedance_create_task_variations`` tool — parallel video task creation.

Creates N independent Seedance video generation tasks in parallel. Seedance
2.0 does not support seeds. Each variation creates a separate task; the
caller polls each task ID via ``seedance_get_task``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import get_capability_registry
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.models import VariationResult, VariationSummary
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedance import SeedanceService
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._parallel import gather_with_timeout, resolve_prompts
from modelark_mcp.tools.seedance_create_task import SeedanceCreateTaskInput


class SeedanceVariationsInput(SeedanceCreateTaskInput):
    """Input for parallel Seedance video task creation.

    Inherits all fields and validators from SeedanceCreateTaskInput
    (prompt, images, videos, audios, model, resolution, duration, etc.)
    and adds variations-specific fields.
    """

    prompt: str | None = Field(
        None, description="Base prompt. Required if variation_prompts is None."
    )
    variations: int = Field(1, ge=1, le=5, description="Number of variations.")
    variation_prompts: list[str] | None = Field(None, description="Explicit prompts per variation.")

    @model_validator(mode="after")
    def validate_prompt_required(self) -> SeedanceVariationsInput:
        if self.prompt is None and not self.variation_prompts:
            raise ValueError("Either prompt or variation_prompts must be provided.")
        return self

    @model_validator(mode="after")
    def validate_prompts_length(self) -> SeedanceVariationsInput:
        if self.variation_prompts and len(self.variation_prompts) != self.variations:
            raise ValueError(f"variation_prompts must have exactly {self.variations} entries")
        return self


class SeedanceVariationsOutput(BaseModel):
    """Output for parallel Seedance video task creation."""

    summary: VariationSummary
    recommended_poll_after_ms: int


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


async def seedance_create_task_variations(
    input: SeedanceVariationsInput, ctx: Context
) -> SeedanceVariationsOutput:
    """Create multiple Seedance video tasks in parallel.

    Each variation creates a separate task. The caller polls each task ID
    via ``seedance_get_task``. Partial failures are captured per variation.
    """
    await ctx.info(f"Starting {input.variations} parallel Seedance task creations")
    await ctx.report_progress(progress=10, total=100)

    log_cost_estimate(product="video", variations=input.variations)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError("BYTEPLUS_MODELARK_API_KEY is not configured.")

    registry = get_capability_registry()
    caps = registry.get_video_capabilities(input.model)

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
                f"outside the supported range [{lo}, {hi}]."
            )

    prompts = resolve_prompts(input.prompt, input.variation_prompts, input.variations)

    images_data: list[dict[str, Any]] | None = (
        [img.model_dump() for img in input.images] if input.images else None
    )
    videos_data: list[dict[str, Any]] | None = (
        [vid.model_dump() for vid in input.videos] if input.videos else None
    )
    audios_data: list[dict[str, Any]] | None = (
        [aud.model_dump() for aud in input.audios] if input.audios else None
    )

    timeout = settings.request_timeout_ms / 1000
    service = SeedanceService()
    limiter = asyncio.Semaphore(5)

    async def _create_single(idx: int) -> VariationResult:
        async with limiter:
            try:
                content = SeedanceService.build_content(
                    prompt=prompts[idx],
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

                task_id, request_id = await service.create_task(request)

                return VariationResult(index=idx, task_id=task_id, request_id=request_id)
            except ProviderError as exc:
                return VariationResult(
                    index=idx,
                    error={
                        "code": exc.code or "PROVIDER_ERROR",
                        "message": exc.message,
                    },
                    request_id=exc.request_id,
                )
            except Exception as exc:
                return VariationResult(
                    index=idx,
                    error={"code": "UNEXPECTED_ERROR", "message": str(exc)},
                )

    coros = [_create_single(i) for i in range(input.variations)]

    try:
        results = await gather_with_timeout(coros, timeout=timeout)
    finally:
        await service.close()

    variation_results: list[VariationResult] = []
    for i, result in enumerate(results):
        if isinstance(result, asyncio.TimeoutError):
            variation_results.append(
                VariationResult(
                    index=i,
                    error={
                        "code": "TIMEOUT",
                        "message": f"Variation {i} timed out",
                    },
                )
            )
        elif isinstance(result, Exception):
            variation_results.append(
                VariationResult(
                    index=i,
                    error={"code": "GATHER_ERROR", "message": str(result)},
                )
            )
        else:
            variation_results.append(result)

    succeeded = sum(1 for r in variation_results if r.artifact is not None or r.task_id is not None)
    failed = input.variations - succeeded

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedance_variations_complete",
        total=input.variations,
        succeeded=succeeded,
        failed=failed,
    )

    return SeedanceVariationsOutput(
        summary=VariationSummary(
            total=input.variations,
            succeeded=succeeded,
            failed=failed,
            variations=variation_results,
        ),
        recommended_poll_after_ms=5000,
    )
