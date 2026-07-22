"""``seed_audio_generate_variations`` tool — parallel audio generation.

Generates N independent audio variations in parallel. Seed Audio does not
support seeds, so variations rely on the stochastic nature of the model.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import AudioReference, MediaSource
from modelark_mcp.domain.models import VariationResult, VariationSummary
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService
from modelark_mcp.tools._parallel import gather_with_timeout, resolve_prompts
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
    audio_references: list[AudioReference] = Field(default_factory=list, max_length=3)
    image_reference: MediaSource | None = None
    output: AudioOutputOptions | None = None
    watermark: AudioWatermarkOptions | None = None
    persist: bool = True

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

    settings = get_settings()
    if not settings.has_seed_audio:
        raise ValueError("BYTEPLUS_SEED_AUDIO_API_KEY is not configured.")

    prompts = resolve_prompts(input.text_prompt, input.variation_prompts, input.variations)

    from modelark_mcp.server import get_artifact_store

    store = get_artifact_store()

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

            response, log_id = await service.generate(request)

            artifact: ArtifactRef | None = None
            source_expiry = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

            if input.persist and response.audio:
                artifact = await store.put_base64(
                    data=response.audio,
                    media_type="audio",
                    mime_type="audio/wav",
                    source_expires_at=source_expiry,
                )
            elif response.url:
                artifact = ArtifactRef(
                    id="provider-url",
                    uri=response.url,
                    media_type="audio",
                    mime_type="audio/wav",
                    created_at=datetime.now(UTC).isoformat(),
                    source_expires_at=source_expiry,
                )

            return VariationResult(index=idx, artifact=artifact, provider_log_id=log_id)
        except ProviderError as exc:
            return VariationResult(
                index=idx,
                error={"code": exc.code or "PROVIDER_ERROR", "message": exc.message},
                request_id=exc.request_id,
            )
        except Exception as exc:
            return VariationResult(
                index=idx,
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
                    error={"code": "TIMEOUT", "message": f"Variation {i} timed out"},
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
        "seed_audio_variations_complete",
        total=input.variations,
        succeeded=succeeded,
        failed=failed,
    )

    return SeedAudioVariationsOutput(
        summary=VariationSummary(
            total=input.variations,
            succeeded=succeeded,
            failed=failed,
            variations=variation_results,
        )
    )
