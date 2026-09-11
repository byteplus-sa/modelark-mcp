"""Poll a MediaKit subtitle burn-in task."""

from __future__ import annotations

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from modelark_mcp.providers.vod_mediakit.subtitles import VodMediaKitSubtitleBurnInService
from modelark_mcp.tools._vod_subtitle_shared import (
    VodSubtitleTaskOutput,
    poll_subtitle_task,
)


class VodGetSubtitleAdditionTaskInput(BaseModel):
    """Input for ``vod_get_subtitle_addition_task``."""

    task_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Task ID returned by vod_add_subtitles.",
    )
    persist_output: bool = Field(
        default=True,
        description="Whether to copy a completed subtitled video into durable artifact storage on first successful poll.",
    )


class VodSubtitleAdditionTaskOutput(VodSubtitleTaskOutput):
    """Normalized status and output of a MediaKit subtitle burn-in task."""


async def vod_get_subtitle_addition_task(
    input: VodGetSubtitleAdditionTaskInput, ctx: Context
) -> VodSubtitleAdditionTaskOutput | ToolResult:
    """Poll and retrieve a BytePlus VOD AI MediaKit subtitle burn-in task.

    On the first successful poll with persist_output enabled, copies the
    temporary MP4 output into durable artifact storage with single-flight
    concurrency protection. Provider success remains visible if persistence
    is skipped or fails. Supports optional MCP task-augmented execution for
    completed-output persistence.
    """
    return await poll_subtitle_task(
        input_task_id=input.task_id,
        persist_output=input.persist_output,
        ctx=ctx,
        service=VodMediaKitSubtitleBurnInService(),
        output_type=VodSubtitleAdditionTaskOutput,
        label="subtitle burn-in",
        log_event="vod_get_subtitle_addition_task_complete",
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
