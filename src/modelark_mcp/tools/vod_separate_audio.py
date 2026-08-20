"""MCP tool for BytePlus VOD OpenAPI voice and background audio separation."""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod.audio_separation import VodAudioSeparationService
from modelark_mcp.providers.vod.schemas import VodStartExecutionRequest
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.tools._errors import provider_error_result


class VodSeparateAudioInput(BaseModel):
    """DirectUrl storage-path input for the voice and background audio separation task."""

    file_name: str = Field(
        min_length=1,
        max_length=2048,
        description="Storage path (FileName) of the media file in the BytePlus VOD space's TOS bucket.",
    )
    space_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="BytePlus VOD space name. Optional when the bucket is unambiguous.",
    )
    bucket_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Storage bucket name bound to the VOD space. Optional when bound by default.",
    )


class VodSeparateAudioOutput(BaseModel):
    """Accepted asynchronous voice and background audio separation submission."""

    provider: Literal["byteplus-vod"] = Field(
        default="byteplus-vod", description="Provider surface that processed the request."
    )
    status: Literal["accepted"] = Field(
        description="Always 'accepted': the separation task is asynchronous."
    )
    request_id: str | None = Field(
        default=None, description="Provider diagnostic request ID, when returned."
    )
    run_id: str = Field(
        description="Provider RunId to pass to vod_get_audio_separation for polling."
    )
    recommended_poll_after_ms: int = Field(
        description="Server-side suggested poll delay; a heuristic, not a provider guarantee."
    )


async def vod_separate_audio(
    input: VodSeparateAudioInput, ctx: Context
) -> VodSeparateAudioOutput | ToolResult:
    """Submit an asynchronous BytePlus VOD voice and background audio separation task.

    Accepts the DirectUrl storage path (FileName, optional SpaceName and
    BucketName) of a media file already stored in a BytePlus VOD space. Submits
    a StartExecution task with Task.Type=AudioExtract, which separates the audio
    into clean vocal and background AAC tracks. Returns an accepted RunId for
    polling with vod_get_audio_separation. The mutation is never retried
    automatically because completion can be ambiguous after a timeout.
    """
    runtime = get_runtime(ctx)
    settings = runtime.settings
    if not settings.has_vod:
        raise ValueError(
            "BYTEPLUS_VOD_ACCESS_KEY_ID and BYTEPLUS_VOD_SECRET_ACCESS_KEY are not "
            "configured. Set both to enable this tool."
        )

    request = VodStartExecutionRequest.model_validate(
        {
            "input": {
                "type": "DirectUrl",
                "direct_url": {
                    "file_name": input.file_name,
                    "space_name": input.space_name,
                    "bucket_name": input.bucket_name,
                },
            }
        }
    )
    owner = get_principal(ctx)
    service = VodAudioSeparationService()
    await ctx.info("Starting BytePlus VOD voice and background audio separation")
    await ctx.report_progress(progress=20, total=100)
    try:
        async with runtime.provider_limiters.acquire("vod", owner):
            submission = await service.submit(request)
    except ProviderError as exc:
        await ctx.error(f"VOD audio separation submission failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await runtime.ownership_store.record("vod", submission.run_id, owner)
    await ctx.report_progress(progress=100, total=100)
    return VodSeparateAudioOutput(
        status="accepted",
        request_id=submission.request_id,
        run_id=submission.run_id,
        recommended_poll_after_ms=3000,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
