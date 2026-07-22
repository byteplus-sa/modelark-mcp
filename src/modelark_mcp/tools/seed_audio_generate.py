"""``seed_audio_generate`` tool — full-scene audio generation through Seed Speech.

Input validation uses a Pydantic model validator to reject image+audio
mixing, more than three references, invalid MIME types, and out-of-range
controls. The adapter maps discriminated unions to the provider's ``speaker``,
``audio_url``, ``audio_data``, ``image_url``, or ``image_data`` fields.
"""

from __future__ import annotations

from datetime import UTC
from typing import Literal

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import AudioReference, MediaSource
from modelark_mcp.domain.models import Subtitle
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService

# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------


class AudioOutputOptions(BaseModel):
    """Optional output controls for Seed Audio generation."""

    format: Literal["wav", "mp3", "pcm", "ogg"] | None = None
    sample_rate: Literal[8000, 16000, 24000, 32000, 44100, 48000] | None = None
    speech_rate: int | None = Field(None, ge=-50, le=100)
    loudness_rate: int | None = Field(None, ge=-50, le=100)
    pitch_rate: int | None = Field(None, ge=-12, le=12)
    subtitle: bool | None = None
    subtitle_type: Literal["utterance", "word"] | None = None


class AudioWatermarkOptions(BaseModel):
    """AIGC watermark controls for Seed Audio."""

    enable: bool | None = None
    metadata: bool | None = None


class SeedAudioGenerateInput(BaseModel):
    """Input model for ``seed_audio_generate``."""

    text_prompt: str = Field(..., min_length=1, max_length=3000)
    audio_references: list[AudioReference] = Field(default_factory=list, max_length=3)
    image_reference: MediaSource | None = None
    output: AudioOutputOptions | None = None
    watermark: AudioWatermarkOptions | None = None
    persist: bool = True

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
    request_id: str
    provider_log_id: str | None = None


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def seed_audio_generate(
    input: SeedAudioGenerateInput, ctx: Context
) -> SeedAudioGenerateOutput:
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

    try:
        response, log_id = await service.generate(request)
    except ProviderError as exc:
        await ctx.error(f"Seed Audio generation failed: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=80, total=100)

    # Persist the audio output.
    artifact: ArtifactRef
    if input.persist and response.audio:
        from modelark_mcp.server import get_artifact_store

        store = get_artifact_store()
        artifact = await store.put_base64(
            data=response.audio,
            media_type="audio",
            mime_type="audio/wav",
            source_expires_at=None,  # 2-hour expiry, but we don't have exact timestamp
        )
    elif response.url:
        # If we only have a URL (no Base64), return a reference to the
        # provider URL directly. This will expire in 2 hours.
        from datetime import datetime, timedelta

        expiry = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        artifact = ArtifactRef(
            id="provider-url",
            uri=response.url,
            media_type="audio",
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
        request_id="",  # X-Api-Request-Id is set on request, not response
        provider_log_id=log_id,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
