"""``seed_audio_generate_variations`` tool — parallel audio generation.

Generates N independent audio variations in parallel. Seed Audio does not
support seeds, so variations rely on the stochastic nature of the model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import AudioReference, MediaSource
from modelark_mcp.domain.models import VariationError, VariationResult, VariationSummary
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService
from modelark_mcp.runtime import billed_provider_slot, get_principal, get_runtime
from modelark_mcp.tools._cost import DEFAULT_MAX_CONCURRENT, estimate_cost, log_cost_estimate
from modelark_mcp.tools._parallel import resolve_prompts, run_variation_batch
from modelark_mcp.tools.seed_audio_generate import AudioOutputOptions, AudioWatermarkOptions


class SeedAudioVariationsInput(BaseModel):
    """Input for parallel Seed Audio generation."""

    text_prompt: str | None = Field(
        None,
        min_length=1,
        max_length=3000,
        description="Base prompt. Required if variation_prompts is None.",
    )
    variations: int = Field(1, ge=1, le=5, description="Number of variations.")
    variation_prompts: list[str] | None = Field(None, description="Explicit prompts per variation.")
    audio_references: list[AudioReference] = Field(
        default_factory=list,
        max_length=3,
        description="Reference audio for voice cloning or scene control (max 3). Mutually exclusive with image_reference.",
    )
    image_reference: MediaSource | None = Field(
        None,
        description="Reference image for visual-guided audio generation. Mutually exclusive with audio_references.",
    )
    output: AudioOutputOptions | None = Field(
        None, description="Optional output format, sample rate, and rate controls."
    )
    watermark: AudioWatermarkOptions | None = Field(
        None, description="Optional AIGC watermark settings."
    )
    persist: bool = Field(
        True, description="Whether to persist generated audio as durable MCP resources."
    )

    @model_validator(mode="after")
    def validate_prompt_required(self) -> SeedAudioVariationsInput:
        if self.text_prompt is None and not self.variation_prompts:
            raise ValueError("Either text_prompt or variation_prompts must be provided.")
        return self

    @model_validator(mode="after")
    def validate_no_media_mixing(self) -> SeedAudioVariationsInput:
        if self.audio_references and self.image_reference:
            raise ValueError("Audio and image references are mutually exclusive.")
        return self

    @model_validator(mode="after")
    def validate_prompts_length(self) -> SeedAudioVariationsInput:
        if self.variation_prompts and len(self.variation_prompts) != self.variations:
            raise ValueError(f"variation_prompts must have exactly {self.variations} entries")
        return self


class SeedAudioVariationsOutput(BaseModel):
    """Output for parallel Seed Audio generation."""

    provider: Literal["byteplus-seed-speech"] = "byteplus-seed-speech"
    model: Literal["seed-audio-1.0"] = "seed-audio-1.0"
    summary: VariationSummary


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


async def seed_audio_generate_variations(
    input: SeedAudioVariationsInput, ctx: Context
) -> SeedAudioVariationsOutput:
    """Generate multiple audio variations in parallel through Seed Speech.

    Seed Audio does not support seeds, so variations rely on the stochastic
    nature of the model. Partial failures are captured per variation.
    """
    await ctx.info(f"Starting {input.variations} parallel Seed Audio generations")
    await ctx.report_progress(progress=10, total=100)

    log_cost_estimate(product="audio", variations=input.variations, duration_seconds=15.0)

    settings = get_settings()
    if not settings.has_seed_audio:
        raise ValueError("BYTEPLUS_SEED_AUDIO_API_KEY is not configured.")

    prompts = resolve_prompts(input.text_prompt, input.variation_prompts, input.variations)

    runtime = get_runtime(ctx)
    store = runtime.artifact_store
    owner = get_principal(ctx)

    audio_refs_data: list[dict[str, Any]] | None = (
        [ref.model_dump() for ref in input.audio_references] if input.audio_references else None
    )
    image_ref_data: dict[str, Any] | None = (
        input.image_reference.model_dump() if input.image_reference else None
    )

    output_dict: dict[str, Any] | None = (
        input.output.model_dump(exclude_none=True) if input.output else None
    )
    watermark_dict: dict[str, Any] | None = (
        input.watermark.model_dump(exclude_none=True) if input.watermark else None
    )

    timeout = settings.request_timeout_ms / 1000
    service = SeedAudioService()

    async def _generate_single(idx: int) -> VariationResult:
        try:
            client_request_id = str(uuid4())
            references = SeedAudioService.build_references(
                audio_refs=audio_refs_data,
                image_ref=image_ref_data,
            )

            request = SeedAudioService.build_request(
                text_prompt=prompts[idx],
                references=references if references else None,
                output=output_dict,
                watermark=watermark_dict,
            )

            async with billed_provider_slot(
                ctx,
                provider="seed-speech",
                product="audio",
                estimated_cost_usd=estimate_cost(
                    product="audio", variations=1, duration_seconds=15.0
                ),
            ):
                response, log_id = await call_with_retry(
                    lambda: service.generate(request, request_id=client_request_id)
                )

            artifact: ArtifactRef | None = None
            source_expiry = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

            if input.persist and response.audio:
                artifact = await store.put_base64(
                    data=response.audio,
                    media_type=MediaType.AUDIO,
                    mime_type="audio/wav",
                    source_expires_at=source_expiry,
                    auth=owner,
                )
            elif response.url:
                artifact = ArtifactRef(
                    id="provider-url",
                    uri=response.url,
                    media_type=MediaType.AUDIO,
                    mime_type="audio/wav",
                    created_at=datetime.now(UTC).isoformat(),
                    source_expires_at=source_expiry,
                )

            return VariationResult(
                index=idx,
                artifact=artifact,
                request_id=client_request_id,
                provider_log_id=log_id,
            )
        except ProviderError as exc:
            return VariationResult(
                index=idx,
                error=VariationError(
                    code=exc.code or "PROVIDER_ERROR",
                    message=exc.message,
                    request_id=exc.request_id,
                    retryable=exc.retryable,
                    ambiguous_completion=bool(exc.ambiguous_completion),
                ),
                request_id=exc.request_id,
            )
        except Exception as exc:
            return VariationResult(
                index=idx,
                error=VariationError(code="UNEXPECTED_ERROR", message=str(exc)),
            )

    try:
        summary = await run_variation_batch(
            count=input.variations,
            timeout=timeout,
            factory=_generate_single,
            max_concurrent=DEFAULT_MAX_CONCURRENT,
        )
    finally:
        await service.close()

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seed_audio_variations_complete",
        total=summary.total,
        succeeded=summary.succeeded,
        failed=summary.failed,
    )

    return SeedAudioVariationsOutput(summary=summary)
