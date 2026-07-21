"""``seedance_get_task`` tool — retrieve the status and output of a Seedance task.

On first successful retrieval, copies 24-hour output URLs into
``ArtifactStore``. Caches the mapping by provider task ID so repeated
status checks do not download twice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastmcp import Context
from pydantic import BaseModel, Field

from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.models import SeedanceTaskUsage
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedance import SeedanceService

SeedanceTaskStatus = Literal[
    "queued",
    "running",
    "cancelled",
    "succeeded",
    "failed",
    "expired",
]


class SeedanceGetTaskInput(BaseModel):
    """Input model for ``seedance_get_task``."""

    task_id: str
    persist_output: bool = True


class SeedanceTaskOutput(BaseModel):
    """Output model for ``seedance_get_task``."""

    task_id: str
    model: str
    status: SeedanceTaskStatus
    created_at: str
    updated_at: str
    error: dict[str, Any] | None = None
    video: ArtifactRef | None = None
    last_frame: ArtifactRef | None = None
    usage: SeedanceTaskUsage | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


# Cache: task_id -> {video_ref, last_frame_ref} so repeated gets don't re-download.
_persistence_cache: dict[str, dict[str, ArtifactRef | None]] = {}


async def seedance_get_task(input: SeedanceGetTaskInput, ctx: Context) -> SeedanceTaskOutput:
    """Retrieve the status and output of a Seedance video generation task.

    On first successful retrieval with ``persist_output=True``, copies
    the 24-hour provider URLs into durable artifact storage. Subsequent
    calls return the cached artifact references without re-downloading.
    """
    await ctx.info(f"Retrieving Seedance task {input.task_id}")
    await ctx.report_progress(progress=20, total=100)

    service = SeedanceService()
    try:
        task, request_id = await service.get_task(input.task_id)
    except ProviderError as exc:
        await ctx.error(f"Failed to retrieve task: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=60, total=100)

    # Normalize error detail.
    error_dict = None
    if task.error and (task.error.code or task.error.message):
        error_dict = {"code": task.error.code, "message": task.error.message}

    # Persist video and last-frame on success (only once per task).
    video_ref: ArtifactRef | None = None
    last_frame_ref: ArtifactRef | None = None

    if task.status == "succeeded" and input.persist_output:
        cache = _persistence_cache.get(input.task_id)
        if cache:
            video_ref = cache.get("video")
            last_frame_ref = cache.get("last_frame")
        else:
            from modelark_mcp.server import get_artifact_store

            store = get_artifact_store()
            source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()

            if task.video_url:
                try:
                    video_ref = await store.copy_from_trusted_url(
                        url=task.video_url,
                        media_type="video",
                        mime_type="video/mp4",
                        source_expires_at=source_expiry,
                    )
                except Exception as exc:
                    from modelark_mcp.observability.logger import warning as log_warning

                    log_warning(
                        "artifact_persist_failed",
                        task_id=input.task_id,
                        media_type="video",
                        error=str(exc),
                    )
                    await ctx.warning(f"Failed to persist video artifact: {exc}")

            if task.last_frame_url:
                try:
                    last_frame_ref = await store.copy_from_trusted_url(
                        url=task.last_frame_url,
                        media_type="image",
                        mime_type="image/jpeg",
                        source_expires_at=source_expiry,
                    )
                except Exception as exc:
                    from modelark_mcp.observability.logger import warning as log_warning

                    log_warning(
                        "artifact_persist_failed",
                        task_id=input.task_id,
                        media_type="last_frame",
                        error=str(exc),
                    )
                    await ctx.warning(f"Failed to persist last-frame artifact: {exc}")

            # Only cache if at least one artifact was persisted.
            # Don't cache failures — allow retry on next poll.
            if video_ref is not None or last_frame_ref is not None:
                _persistence_cache[input.task_id] = {
                    "video": video_ref,
                    "last_frame": last_frame_ref,
                }

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedance_task_retrieved",
        task_id=input.task_id,
        status=task.status,
        request_id=request_id,
    )

    # Normalize settings from the generation config.
    settings_dict: dict[str, Any] = dict(task.content) if task.content else {}

    return SeedanceTaskOutput(
        task_id=task.id,
        model=task.model,
        status=task.status,  # type: ignore[arg-type]
        created_at=SeedanceService.get_created_at(task),
        updated_at=SeedanceService.get_updated_at(task),
        error=error_dict,
        video=video_ref,
        last_frame=last_frame_ref,
        usage=SeedanceService.extract_usage(task),
        settings=settings_dict,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
