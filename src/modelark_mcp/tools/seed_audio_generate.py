"""``seed_audio_generate`` tool — full-scene audio generation through Seed Speech.

Input validation uses a Pydantic model validator to reject image+audio
mixing, more than three references, invalid MIME types, and out-of-range
controls. The adapter maps discriminated unions to the provider's ``speaker``,
``audio_url``, ``audio_data``, ``image_url``, or ``image_data`` fields.
"""

from __future__ import annotations

from datetime import UTC
from typing import Literal
from uuid import uuid4

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import AudioReference, MediaSource
from modelark_mcp.domain.models import Subtitle
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService
from modelark_mcp.runtime import billed_provider_slot, get_principal, get_runtime
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._errors import provider_error_result

# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------


class AudioOutputOptions(BaseModel):
    """Optional output controls for Seed Audio generation."""

    format: Literal["wav", "mp3", "pcm", "ogg"] | None = Field(
        None, description="Output audio format. Defaults to wav if not specified."
    )
    sample_rate: Literal[8000, 16000, 24000, 32000, 44100, 48000] | None = Field(
        None, description="Output sample rate in Hz. Defaults to provider setting if not specified."
    )
    speech_rate: int | None = Field(
        None, ge=-50, le=100, description="Speech speed adjustment. -50 (slowest) to 100 (fastest)."
    )
    loudness_rate: int | None = Field(
        None,
        ge=-50,
        le=100,
        description="Volume/loudness adjustment. -50 (quietest) to 100 (loudest).",
    )
    pitch_rate: int | None = Field(
        None, ge=-12, le=12, description="Pitch adjustment in semitones. -12 to +12."
    )
    subtitle: bool | None = Field(
        None, description="Whether to return timestamped subtitles in the response."
    )
    subtitle_type: Literal["utterance", "word"] | None = Field(
        None, description="Subtitle granularity: utterance-level or word-level timestamps."
    )


class AudioWatermarkOptions(BaseModel):
    """AIGC watermark controls for Seed Audio."""

    enable: bool | None = Field(None, description="Enable or disable AIGC audio watermarking.")
    metadata: bool | None = Field(
        None, description="Whether to embed AIGC metadata in the audio file."
    )


class SeedAudioGenerateInput(BaseModel):
    """Input model for ``seed_audio_generate``."""

    text_prompt: str = Field(
        ...,
        min_length=1,
        max_length=3000,
        description="Text describing the audio to generate (up to 3,000 characters).",
    )
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
        True, description="Whether to persist the generated audio as a durable MCP resource."
    )

    @model_validator(mode="after")
    def validate_no_media_mixing(self) -> SeedAudioGenerateInput:
        """Reject mixing audio and image references."""
        if self.audio_references and self.image_reference:
            raise ValueError(
                "Audio references and image reference are mutually exclusive. "
                "Use one or the other, not both."
            )
        return self


class SeedAudioGenerateOutput(BaseModel):
    """Output model for ``seed_audio_generate``."""

    provider: Literal["byteplus-seed-speech"] = "byteplus-seed-speech"
    model: Literal["seed-audio-1.0"] = "seed-audio-1.0"
    duration_seconds: float
    billing_duration_seconds: float
    artifact: ArtifactRef
    subtitle: Subtitle | None = None
    request_id: str | None = None
    provider_log_id: str | None = None


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def seed_audio_generate(
    input: SeedAudioGenerateInput, ctx: Context
) -> SeedAudioGenerateOutput | ToolResult:
    """Generate full-scene audio through Seed Speech.

    Accepts a text prompt (up to 3,000 characters) and optional audio or
    image references for voice cloning and scene control. Returns a durable
    artifact reference that survives the 2-hour provider URL expiry.
    """
    await ctx.info("Starting Seed Audio generation")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_seed_audio:
        raise ValueError(
            "BYTEPLUS_SEED_AUDIO_API_KEY is not configured. "
            "Set it in .env to enable Seed Audio tools."
        )

    service = SeedAudioService()
    await ctx.report_progress(progress=30, total=100)

    # Build provider references from domain input.
    audio_refs_data = None
    image_ref_data = None

    if input.audio_references:
        audio_refs_data = [ref.model_dump() for ref in input.audio_references]
    if input.image_reference:
        image_ref_data = input.image_reference.model_dump()

    references = SeedAudioService.build_references(
        audio_refs=audio_refs_data,
        image_ref=image_ref_data,
    )

    output_dict = None
    if input.output:
        output_dict = input.output.model_dump(exclude_none=True)

    watermark_dict = None
    if input.watermark:
        watermark_dict = input.watermark.model_dump(exclude_none=True)

    request = SeedAudioService.build_request(
        text_prompt=input.text_prompt,
        references=references if references else None,
        output=output_dict,
        watermark=watermark_dict,
    )

    await ctx.report_progress(progress=50, total=100)

    estimated_cost = log_cost_estimate(product="audio", variations=1, duration_seconds=15.0)
    client_request_id = str(uuid4())

    try:
        async with billed_provider_slot(
            ctx,
            provider="seed-speech",
            product="audio",
            estimated_cost_usd=estimated_cost,
        ):
            response, log_id = await call_with_retry(
                lambda: service.generate(request, request_id=client_request_id)
            )
    except ProviderError as exc:
        await ctx.error(f"Seed Audio generation failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=80, total=100)

    # Persist the audio output.
    artifact: ArtifactRef
    if input.persist and response.audio:
        store = get_runtime(ctx).artifact_store
        artifact = await store.put_base64(
            data=response.audio,
            media_type=MediaType.AUDIO,
            mime_type="audio/wav",
            source_expires_at=None,  # 2-hour expiry, but we don't have exact timestamp
            auth=get_principal(ctx),
        )
    elif response.url:
        # If we only have a URL (no Base64), return a reference to the
        # provider URL directly. This will expire in 2 hours.
        from datetime import datetime, timedelta

        expiry = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        artifact = ArtifactRef(
            id="provider-url",
            uri=response.url,
            media_type=MediaType.AUDIO,
            mime_type="audio/wav",
            created_at=datetime.now(UTC).isoformat(),
            source_expires_at=expiry,
        )
    else:
        raise ValueError("Provider returned neither Base64 audio nor URL.")

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seed_audio_complete",
        duration=response.duration,
        billing_duration=response.original_duration,
        artifact_id=artifact.id,
    )

    return SeedAudioGenerateOutput(
        duration_seconds=response.duration or 0.0,
        billing_duration_seconds=response.original_duration or 0.0,
        artifact=artifact,
        subtitle=SeedAudioService.extract_subtitle(response),
        request_id=client_request_id,
        provider_log_id=log_id,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
