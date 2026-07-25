"""``speech_to_text_create_task`` tool — submit audio for transcription via LAS ASR.

Accepts audio via URL (always), Base64 (requires TOS), or local file path
(stdio + TOS). When TOS is configured, Base64/file audio is uploaded to TOS
and the resulting presigned URL is passed to the LAS ASR submit endpoint.
Without TOS, only URL input is accepted. Returns a task ID for polling via
``speech_to_text_get_result``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import Settings, get_settings
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.las.asr import LasAsrService
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.tos.client import TosGateway
from modelark_mcp.runtime import billed_provider_slot, get_principal, get_runtime
from modelark_mcp.security.media_policy import (
    validate_audio_mime,
    validate_video_mime,
)
from modelark_mcp.security.url_policy import validate_url
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._errors import provider_error_result

_FORMAT_TO_MIME: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "raw": "audio/pcm",
    "flac": "audio/flac",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
}

_STT_MAX_BYTES = 200 * 1024 * 1024


class AsrAudioInput(BaseModel):
    """Audio source for STT — resolved to a URL for the provider."""

    audio_url: str | None = Field(
        None,
        description="HTTPS URL of the audio file. Always available.",
    )
    audio_data: str | None = Field(
        None,
        description="Base64-encoded audio bytes. Requires TOS configured. Mutually exclusive with other inputs.",
    )
    audio_file_path: str | None = Field(
        None,
        description="Absolute local file path. stdio transport only. Requires TOS configured. Mutually exclusive with other inputs.",
    )
    audio_format: Literal["wav", "mp3", "ogg", "raw", "flac", "mp4", "mov", "mkv"] = Field(
        ...,
        description="Audio/video format: wav, mp3, ogg, raw, flac (audio); mp4, mov, mkv (video).",
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

    enable_punc: bool | None = Field(
        None, description="Enable automatic punctuation. Default: true."
    )
    enable_itn: bool | None = Field(
        None, description="Enable inverse text normalization (number formatting). Default: true."
    )
    enable_speaker_info: bool | None = Field(
        None, description="Enable speaker diarization (up to 10 speakers)."
    )
    enable_lid: bool | None = Field(None, description="Enable automatic language identification.")
    show_utterances: bool | None = Field(
        None, description="Return utterance-level segments with timestamps."
    )
    show_words: bool | None = Field(
        None, description="Return word-level timestamps within utterances."
    )


class SpeechToTextCreateTaskInput(BaseModel):
    """Input model for ``speech_to_text_create_task``."""

    audio: AsrAudioInput
    options: AsrRequestOptions | None = Field(
        None,
        description="Optional transcription feature toggles.",
    )
    operator: Literal["las_asr_pro", "las_asr"] | None = Field(
        None,
        description="Override LAS operator: 'las_asr_pro' (enhanced) or 'las_asr' (standard). Defaults to LAS_DEFAULT_OPERATOR.",
    )


class SpeechToTextCreateTaskOutput(BaseModel):
    """Output model for ``speech_to_text_create_task``."""

    task_id: str
    status: Literal["queued"] = "queued"
    recommended_poll_after_ms: int


async def _resolve_audio_url(audio_input: AsrAudioInput, settings: Settings, ctx: Context) -> str:
    """Resolve audio input to a URL for the LAS ASR provider.

    URL input passes through directly. Base64 and file_path inputs require
    TOS — the data is uploaded and a presigned URL is returned.
    """
    if audio_input.audio_url:
        return audio_input.audio_url

    if not settings.has_tos:
        raise ValueError(
            "Base64 or file_path audio input requires TOS credentials. "
            "Set TOS_ACCESS_KEY, TOS_SECRET_KEY, and TOS_BUCKET, or provide audio_url."
        )

    mime_type = _FORMAT_TO_MIME[audio_input.audio_format]

    if mime_type.startswith("audio/"):
        validate_audio_mime(mime_type)
    else:
        validate_video_mime(mime_type)

    max_bytes = _STT_MAX_BYTES
    prefix = "stt-input"
    key = f"{prefix}/{audio_input.audio_format}/{uuid4()}"
    gateway = TosGateway()

    try:
        async with billed_provider_slot(
            ctx, provider="tos", product="upload", estimated_cost_usd=0.0
        ):
            if audio_input.audio_file_path is not None:
                if settings.mcp_transport != "stdio":
                    raise ValueError("file_path input is only supported in stdio transport mode.")
                path = Path(audio_input.audio_file_path).expanduser().resolve()
                if not path.is_file():
                    raise ValueError(f"File not found: {audio_input.audio_file_path}")
                file_size = path.stat().st_size
                if file_size > max_bytes:
                    raise ValueError(
                        f"Audio file size ({file_size} bytes) exceeds limit ({max_bytes} bytes)."
                    )
                file_path_str = str(path)
                await call_with_retry(
                    lambda: gateway.upload_file(
                        key=key, file_path=file_path_str, mime_type=mime_type
                    )
                )
            elif audio_input.audio_data is not None:
                from modelark_mcp.security.media_policy import decode_base64_safely

                raw = decode_base64_safely(audio_input.audio_data, max_bytes, label="audio")
                data_bytes = raw
                await call_with_retry(
                    lambda: gateway.upload_bytes(key=key, data=data_bytes, mime_type=mime_type)
                )
            url = await gateway.presign_get(key=key)
    finally:
        await gateway.close()

    return url


async def speech_to_text_create_task(
    input: SpeechToTextCreateTaskInput, ctx: Context
) -> SpeechToTextCreateTaskOutput | ToolResult:
    """Submit audio for speech-to-text transcription via BytePlus LAS ASR.

    Accepts audio via URL (always), Base64 (requires TOS), or local file path
    (stdio + TOS). Returns a task ID — use ``speech_to_text_get_result`` to
    poll for the transcription.
    """
    await ctx.info("Starting speech-to-text task submission")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_las:
        raise ValueError(
            "BYTEPLUS_LAS_API_KEY is not configured. Set it in .env to enable speech-to-text tools."
        )

    await ctx.report_progress(progress=30, total=100)

    audio_url = await _resolve_audio_url(input.audio, settings, ctx)

    await ctx.report_progress(progress=50, total=100)

    operator_id = input.operator or settings.las_default_operator
    operator_version = LasAsrService.derive_operator_version(operator_id)
    resource = settings.las_default_resource if operator_id == "las_asr_pro" else None

    options = input.options
    request = LasAsrService.build_submit_request(
        audio_url=audio_url,
        audio_format=input.audio.audio_format,
        resource=resource,
        enable_punc=options.enable_punc if options else None,
        enable_itn=options.enable_itn if options else None,
        enable_speaker_info=options.enable_speaker_info if options else None,
        enable_lid=options.enable_lid if options else None,
        show_utterances=options.show_utterances if options else None,
        show_words=options.show_words if options else None,
        operator_id=operator_id,
        operator_version=operator_version,
    )

    estimated_cost = log_cost_estimate(product="stt", variations=1, duration_seconds=60.0)

    service = LasAsrService()
    try:
        async with billed_provider_slot(
            ctx,
            provider="las",
            product="stt",
            estimated_cost_usd=estimated_cost,
        ):
            response, request_id = await call_with_retry(lambda: service.submit(request))
    except ProviderError as exc:
        await ctx.error(f"Speech-to-text task submission failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    task_id = response.metadata.task_id

    await get_runtime(ctx).ownership_store.record(task_id, get_principal(ctx))

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "stt_task_created",
        task_id=task_id,
        operator=operator_id,
        request_id=request_id,
    )

    return SpeechToTextCreateTaskOutput(
        task_id=task_id,
        status="queued",
        recommended_poll_after_ms=3000,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
