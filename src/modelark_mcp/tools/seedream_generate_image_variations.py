"""``seedream_generate_image_variations`` tool — parallel image generation.

Generates N independent image variations in parallel using ``asyncio.gather``.
Each variation gets a distinct seed (when supported) and may use its own
prompt (via ``variation_prompts``). Partial failures are captured per
variation — one bad variation does not fail the batch.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import get_capability_registry
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import MediaSource
from modelark_mcp.domain.models import VariationResult, VariationSummary
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedream import SeedreamService
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._parallel import gather_with_timeout, generate_seeds, resolve_prompts


class SeedreamVariationsInput(BaseModel):
    """Input for parallel Seedream image generation."""

    prompt: str | None = Field(
        None, description="Base prompt for all variations. Required if variation_prompts is None."
    )
    variations: int = Field(1, ge=1, le=10, description="Number of variations.")
    variation_prompts: list[str] | None = Field(
        None,
        description="Explicit prompts per variation. If provided, overrides prompt and must have `variations` entries.",
    )
    base_seed: int | None = Field(
        None,
        ge=-1,
        le=2147483647,
        description="Base seed. None = provider-randomized. -1 = client-randomized. N = deterministic (N+i per variation).",
    )
    images: list[MediaSource] | None = None
    model: str | None = None
    size: str | None = None
    output_format: Literal["png", "jpeg"] | None = None
    response_format: Literal["url", "b64_json"] | None = None
    watermark: bool | None = None
    prompt_optimization: Literal["standard", "fast"] | None = None
    persist: bool = True

    @model_validator(mode="after")
    def validate_prompt_required(self) -> SeedreamVariationsInput:
        if self.prompt is None and not self.variation_prompts:
            raise ValueError("Either prompt or variation_prompts must be provided.")
        return self

    @model_validator(mode="after")
    def validate_prompts_length(self) -> SeedreamVariationsInput:
        if self.variation_prompts and len(self.variation_prompts) != self.variations:
            raise ValueError(
                f"variation_prompts must have exactly {self.variations} entries, "
                f"got {len(self.variation_prompts)}"
            )
        return self


class SeedreamVariationsOutput(BaseModel):
    """Output for parallel Seedream image generation."""

    provider: Literal["byteplus-modelark"] = "byteplus-modelark"
    model: str
    created_at: str
    summary: VariationSummary


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


async def seedream_generate_image_variations(
    input: SeedreamVariationsInput, ctx: Context
) -> SeedreamVariationsOutput:
    """Generate multiple image variations in parallel through ModelArk Seedream.

    Each variation is an independent generation with its own seed (when
    supported). Partial failures are captured — one bad variation does not
    fail the batch.
    """
    await ctx.info(f"Starting {input.variations} parallel Seedream generations")
    await ctx.report_progress(progress=10, total=100)

    log_cost_estimate(product="image", variations=input.variations)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError("BYTEPLUS_MODELARK_API_KEY is not configured.")

    registry = get_capability_registry()
    caps = registry.get_image_capabilities(input.model)

    if len(input.images or []) > caps.max_references:
        raise ValueError(
            f"Model '{caps.model_id}' supports at most {caps.max_references} "
            f"reference images, got {len(input.images or [])}."
        )
    registry.validate_output_format(input.model, input.output_format)
    registry.validate_image_size(input.model, input.size)

    seeds = generate_seeds(input.base_seed, input.variations)
    prompts = resolve_prompts(input.prompt, input.variation_prompts, input.variations)

    from modelark_mcp.server import get_artifact_store

    store = get_artifact_store()

    images_data: list[dict[str, Any]] | None = (
        [src.model_dump() for src in input.images] if input.images else None
    )
    timeout = settings.request_timeout_ms / 1000

    service = SeedreamService()
    limiter = asyncio.Semaphore(5)

    async def _generate_single(idx: int) -> VariationResult:
        async with limiter:
            try:
                request = SeedreamService.build_request(
                    model=caps.model_id,
                    prompt=prompts[idx],
                    images=images_data,
                    size=input.size,
                    seed=seeds[idx],
                    output_format=input.output_format,
                    response_format=input.response_format,
                    watermark=input.watermark,
                    prompt_optimization=input.prompt_optimization,
                )

                response, request_id = await service.generate(request)

                artifact: ArtifactRef | None = None
                source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
                mime = f"image/{input.output_format}" if input.output_format else "image/png"

                if input.persist and response.data:
                    item = response.data[0]
                    if item.b64_json:
                        artifact = await store.put_base64(
                            data=item.b64_json,
                            media_type="image",
                            mime_type=mime,
                            source_expires_at=source_expiry,
                        )
                    elif item.url:
                        artifact = await store.copy_from_trusted_url(
                            url=item.url,
                            media_type="image",
                            mime_type=mime,
                            source_expires_at=source_expiry,
                        )
                elif not input.persist and response.data:
                    item = response.data[0]
                    if item.url:
                        artifact = ArtifactRef(
                            id="provider-url",
                            uri=item.url,
                            media_type="image",
                            mime_type=mime,
                            created_at=datetime.now(UTC).isoformat(),
                            source_expires_at=source_expiry,
                        )

                return VariationResult(
                    index=idx,
                    seed=seeds[idx],
                    artifact=artifact,
                    request_id=request_id,
                )
            except ProviderError as exc:
                return VariationResult(
                    index=idx,
                    seed=seeds[idx],
                    error={
                        "code": exc.code or "PROVIDER_ERROR",
                        "message": exc.message,
                    },
                    request_id=exc.request_id,
                )
            except Exception as exc:
                return VariationResult(
                    index=idx,
                    seed=seeds[idx],
                    error={"code": "UNEXPECTED_ERROR", "message": str(exc)},
                )

    coros = [_generate_single(i) for i in range(input.variations)]

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
                    seed=seeds[i],
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
                    seed=seeds[i],
                    error={"code": "GATHER_ERROR", "message": str(result)},
                )
            )
        else:
            variation_results.append(result)

    succeeded = sum(1 for r in variation_results if r.artifact is not None or r.task_id is not None)
    failed = input.variations - succeeded

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedream_variations_complete",
        total=input.variations,
        succeeded=succeeded,
        failed=failed,
    )

    return SeedreamVariationsOutput(
        model=caps.model_id,
        created_at=datetime.now(UTC).isoformat(),
        summary=VariationSummary(
            total=input.variations,
            succeeded=succeeded,
            failed=failed,
            variations=variation_results,
        ),
    )
