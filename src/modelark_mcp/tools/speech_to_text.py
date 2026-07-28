"""``speech_to_text`` tool — transcribe audio via Seed Speech ASR (synchronous).

Resolves audio to raw bytes (URL → SSRF-safe download, Base64 → decode, file →
read), submits to Seed Speech ASR via HTTP, polls until complete, and returns
the ``TranscriptionResult`` in a single response. No task ID, no TOS upload,
no second tool — the HTTP submit + poll is fully contained within one tool
invocation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.transcription import TranscriptionResult
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.seed_speech.asr import SeedSpeechAsrService
from modelark_mcp.runtime import billed_provider_slot, get_runtime
from modelark_mcp.security.media_policy import decode_base64_safely
from modelark_mcp.security.url_policy import validate_url
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._errors import provider_error_result

_STT_MAX_BYTES = 200 * 1024 * 1024
_BYTES_PER_SECOND_16KHZ_MONO_16BIT = 32000


def _estimate_duration_seconds(num_bytes: int) -> float:
    return max(num_bytes / _BYTES_PER_SECOND_16KHZ_MONO_16BIT, 1.0)


class AsrAudioInput(BaseModel):
    """Audio source — resolved to raw bytes for HTTP submit."""

    audio_url: str | None = Field(None, description="HTTPS URL of the audio file.")
    audio_data: str | None = Field(
        None, description="Base64-encoded audio bytes. Mutually exclusive with other inputs."
    )
    audio_file_path: str | None = Field(
        None,
        description="Absolute local file path. stdio transport only. Mutually exclusive with other inputs.",
    )
    audio_format: Literal["wav", "mp3", "ogg", "raw", "flac"] = Field(
        ...,
        description="Audio format: wav, mp3, ogg, raw, flac.",
    )

    @model_validator(mode="after")
    def validate_exactly_one_source(self) -> AsrAudioInput:
        provided = sum(1 for v in (self.audio_url, self.audio_data, self.audio_file_path) if v)
        if provided != 1:
            raise ValueError("Provide exactly one of audio_url, audio_data, or audio_file_path.")
        if self.audio_url:
            validate_url(self.audio_url)
        return self


class AsrRequestOptions(BaseModel):
    """Optional transcription feature toggles."""

    language: str = Field("en-US", description="BCP-47 language code.")
    enable_punc: bool | None = Field(None, description="Enable punctuation.")
    enable_itn: bool | None = Field(None, description="Enable ITN.")


class SpeechToTextInput(BaseModel):
    """Input for the ``speech_to_text`` tool."""

    audio: AsrAudioInput
    options: AsrRequestOptions | None = None


class SpeechToTextOutput(BaseModel):
    """Output for the ``speech_to_text`` tool."""

    result: TranscriptionResult = Field(
        ..., description="Full transcription result with text, utterances, and timing."
    )
    log_id: str | None = Field(None, description="Provider-side log ID for troubleshooting.")


async def _resolve_audio_bytes(audio: AsrAudioInput, ctx: Context) -> bytes:
    """Resolve any input source to raw audio bytes."""
    if audio.audio_url:
        downloaded = await get_runtime(ctx).safe_downloader.download(
            audio.audio_url,
            trusted_hosts=lambda _host: True,
            max_bytes=_STT_MAX_BYTES,
        )
        return downloaded.body
    if audio.audio_data:
        return decode_base64_safely(audio.audio_data, _STT_MAX_BYTES, label="audio")
    p = Path(audio.audio_file_path or "").expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"Audio file not found: {p}")
    return p.read_bytes()


async def speech_to_text(input: SpeechToTextInput, ctx: Context) -> SpeechToTextOutput | ToolResult:
    """Transcribe audio to text via Seed Speech ASR (single synchronous call).

    Accepts audio via URL, Base64, or local file path (stdio only). Returns the
    complete ``TranscriptionResult`` directly — no task ID, no polling.
    """
    await ctx.info("Starting speech-to-text transcription")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_stt:
        raise ValueError(
            "SEED_SPEECH_ASR_API_KEY is not configured. Set it in .env to enable speech-to-text."
        )

    try:
        audio_bytes = await _resolve_audio_bytes(input.audio, ctx)
    except (ProviderError, ValueError) as exc:
        await ctx.error(f"Audio resolution failed: {exc}")
        if isinstance(exc, ProviderError):
            return provider_error_result(exc)
        return ToolResult(
            content=[{"type": "text", "text": f"Invalid audio input: {exc}"}],
            is_error=True,
        )

    await ctx.report_progress(progress=30, total=100)
    duration_est = _estimate_duration_seconds(len(audio_bytes))
    estimated_cost = log_cost_estimate(product="stt", variations=1, duration_seconds=duration_est)

    options = input.options or AsrRequestOptions()
    service = SeedSpeechAsrService()
    try:
        async with billed_provider_slot(
            ctx,
            provider="seed-speech",
            product="stt",
            estimated_cost_usd=estimated_cost,
        ):
            result, log_id = await call_with_retry(
                lambda: service.transcribe(
                    audio_bytes=audio_bytes,
                    audio_format=input.audio.audio_format,
                    language=options.language,
                    enable_punc=options.enable_punc,
                    enable_itn=options.enable_itn,
                    poll_interval=settings.seed_speech_asr_poll_interval_seconds,
                    poll_max=settings.seed_speech_asr_poll_max_seconds,
                )
            )
    except ProviderError as exc:
        await ctx.error(f"Speech-to-text failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "stt_completed",
        chars=len(result.text),
        utterances=len(result.utterances),
        log_id=log_id,
    )
    return SpeechToTextOutput(result=result, log_id=log_id)


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
