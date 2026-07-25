"""``speech_to_text_get_result`` tool — retrieve STT transcription results.

Polls the LAS ASR service for task status and returns the full transcription
when complete, including utterances, word-level timestamps, and speaker labels
if enabled.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.transcription import (
    AsrTaskStatus,
    TranscriptionResult,
    TranscriptionUtterance,
    TranscriptionWord,
)
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.las.asr import LasAsrService
from modelark_mcp.providers.las.schemas import LasAsrPollResponse
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.tools._errors import provider_error_result


class SpeechToTextGetResultInput(BaseModel):
    """Input model for ``speech_to_text_get_result``."""

    task_id: str = Field(..., description="Task ID returned by speech_to_text_create_task.")
    operator: Literal["las_asr_pro", "las_asr"] | None = Field(
        None,
        description="Override LAS operator. Must match the submit call. Defaults to LAS_DEFAULT_OPERATOR.",
    )


class SpeechToTextGetResultOutput(BaseModel):
    """Output model for ``speech_to_text_get_result``."""

    task_id: str
    status: AsrTaskStatus
    result: TranscriptionResult | None = None
    error: str | None = None
    request_id: str | None = None


def _map_result(response: LasAsrPollResponse) -> TranscriptionResult:
    """Map the LAS ASR poll response to the domain TranscriptionResult."""
    data = response.data
    if data is None or data.result is None:
        return TranscriptionResult(text="")

    result = data.result
    utterances = [
        TranscriptionUtterance(
            text=u.text,
            start_time_ms=u.start_time,
            end_time_ms=u.end_time,
            words=[
                TranscriptionWord(
                    text=w.text,
                    confidence=w.confidence,
                    start_time_ms=w.start_time,
                    end_time_ms=w.end_time,
                )
                for w in u.words
            ],
            speaker_id=u.additions.get("speaker_id") if u.additions else None,
            channel_id=u.additions.get("channel_id") if u.additions else None,
        )
        for u in result.utterances
    ]

    duration_ms: int | None = None
    if data.audio_info and data.audio_info.duration:
        duration_ms = data.audio_info.duration
    elif result.additions and result.additions.get("duration"):
        try:
            duration_ms = int(result.additions["duration"])
        except (ValueError, TypeError):
            duration_ms = None

    return TranscriptionResult(
        text=result.text,
        utterances=utterances,
        duration_ms=duration_ms,
    )


def _normalize_status(task_status: str, business_code: str, error_msg: str) -> AsrTaskStatus:
    """Normalize the LAS task_status to the domain AsrTaskStatus."""
    upper = task_status.upper()
    if upper == "COMPLETED":
        return AsrTaskStatus.COMPLETED
    if upper == "FAILED" or (business_code != "0" and error_msg):
        return AsrTaskStatus.FAILED
    if upper == "ACCEPTED":
        return AsrTaskStatus.ACCEPTED
    return AsrTaskStatus.PENDING


async def speech_to_text_get_result(
    input: SpeechToTextGetResultInput, ctx: Context
) -> SpeechToTextGetResultOutput | ToolResult:
    """Retrieve the result of a speech-to-text transcription task.

    Polls the LAS ASR service for task status. Returns the full transcription
    when complete, including utterances, word-level timestamps, and speaker
    labels if enabled.
    """
    await ctx.info(f"Retrieving speech-to-text task {input.task_id}")
    await ctx.report_progress(progress=20, total=100)

    settings = get_settings()
    runtime = get_runtime(ctx)
    owner = get_principal(ctx)
    await runtime.ownership_store.require_owner(input.task_id, owner)

    operator_id = input.operator or settings.las_default_operator
    operator_version = LasAsrService.derive_operator_version(operator_id)

    service = LasAsrService()
    try:
        response, request_id = await call_with_retry(
            lambda: service.poll(input.task_id, operator_id, operator_version)
        )
    except ProviderError as exc:
        await ctx.error(f"Failed to retrieve speech-to-text task: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=80, total=100)

    metadata = response.metadata
    status = _normalize_status(metadata.task_status, metadata.business_code, metadata.error_msg)

    result: TranscriptionResult | None = None
    error: str | None = None

    if status == AsrTaskStatus.COMPLETED:
        result = _map_result(response)
    elif status == AsrTaskStatus.FAILED:
        error = metadata.error_msg or f"Task failed with business_code={metadata.business_code}"

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "stt_task_retrieved",
        task_id=input.task_id,
        status=status.value,
        request_id=request_id,
    )

    return SpeechToTextGetResultOutput(
        task_id=metadata.task_id,
        status=status,
        result=result,
        error=error,
        request_id=request_id,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
