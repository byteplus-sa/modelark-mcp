"""Shared polling and persistence for MediaKit subtitle video tasks."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import AnyUrl, BaseModel, Field, UrlConstraints, model_validator

from ark_mcp.artifacts.store import ArtifactPersistenceError
from ark_mcp.domain.artifacts import ArtifactRef, MediaType
from ark_mcp.domain.errors import ProviderError
from ark_mcp.observability.logger import info as log_info
from ark_mcp.providers.retry import call_with_retry
from ark_mcp.providers.vod_mediakit.schemas import SubtitleTask
from ark_mcp.runtime import get_principal, get_runtime
from ark_mcp.security.auth_context import PrincipalContext
from ark_mcp.security.media_policy import get_media_limits
from ark_mcp.tools._errors import provider_error_result
from ark_mcp.tools._task_execution import context_log
from ark_mcp.tools._vod_shared import VodArtifactPersistenceIssue

HttpsUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=["https"])]


class SubtitleTaskService(Protocol):
    """Provider-service contract required by the shared poller."""

    async def get(self, task_id: str) -> SubtitleTask: ...

    async def close(self) -> None: ...


class VodSubtitleTaskFailure(BaseModel):
    """Safe provider failure detail for a subtitle video task."""

    code: str | None = Field(default=None, description="Provider failure code, when returned.")
    message: str = Field(
        description="Safe provider failure explanation without credentials or signed URLs."
    )


class VodSubtitleTaskOutput(BaseModel):
    """Normalized state and output shared by subtitle addition and removal tasks."""

    provider: Literal["byteplus-vod-mediakit"] = Field(
        default="byteplus-vod-mediakit",
        description="Provider surface that processed the subtitle operation.",
    )
    task_id: str = Field(description="Provider subtitle-operation task ID.")
    status: Literal["processing", "succeeded", "failed"] = Field(
        description="Normalized task state: processing, succeeded, or failed."
    )
    provider_status: str | None = Field(
        default=None, description="Raw provider status label, when returned."
    )
    request_id: str | None = Field(
        default=None, description="Provider diagnostic request ID, when returned."
    )
    duration_seconds: float | None = Field(
        default=None, ge=0, description="Output video duration in seconds, when reported."
    )
    resolution: str | None = Field(
        default=None, description="Output resolution label, when reported by MediaKit."
    )
    created_at: str | None = Field(
        default=None,
        description="ISO-8601 task creation time normalized from the provider response.",
    )
    finished_at: str | None = Field(
        default=None,
        description="ISO-8601 terminal task time normalized from the provider response.",
    )
    video: ArtifactRef | None = Field(
        default=None,
        description="Durable processed-video artifact when best-effort persistence succeeds.",
    )
    source_url: HttpsUrl | None = Field(
        default=None,
        description="Expiring provider output URL for a succeeded task, preserved if persistence is skipped or fails.",
    )
    source_expires_at: str | None = Field(
        default=None,
        description="ISO-8601 expiry for source_url, normalized from the provider response.",
    )
    persistence: Literal["not_applicable", "not_requested", "persisted", "failed"] = Field(
        description="Outcome of durable artifact persistence, independent of provider success."
    )
    persistence_issue: VodArtifactPersistenceIssue | None = Field(
        default=None,
        description="Safe explanation when a succeeded output could not be persisted durably.",
    )
    error: VodSubtitleTaskFailure | None = Field(
        default=None, description="Provider failure code and safe message for a failed task."
    )

    @model_validator(mode="after")
    def validate_state(self) -> VodSubtitleTaskOutput:
        if self.status == "processing":
            if self.source_url is not None or self.video is not None:
                raise ValueError("processing output must not carry output metadata")
            if self.persistence != "not_applicable":
                raise ValueError("processing output must set persistence=not_applicable")
        elif self.status == "succeeded":
            if self.source_url is None:
                raise ValueError("succeeded output requires source_url")
            if self.persistence == "not_applicable":
                raise ValueError("succeeded output must not use not_applicable persistence")
            if self.persistence == "persisted" and (
                self.video is None or self.persistence_issue is not None
            ):
                raise ValueError("persisted output requires video and forbids a persistence issue")
            if self.persistence == "failed" and self.persistence_issue is None:
                raise ValueError("failed persistence requires a persistence issue")
            if self.persistence == "not_requested" and (
                self.video is not None or self.persistence_issue is not None
            ):
                raise ValueError("not_requested persistence forbids video and persistence issue")
            if self.error is not None:
                raise ValueError("succeeded output must not carry a provider failure")
        elif self.error is None:
            raise ValueError("failed output requires provider failure detail")
        return self


async def persist_subtitle_output(
    ctx: Context,
    owner: PrincipalContext,
    task_id: str,
    task: SubtitleTask,
    persist_output: bool,
    *,
    label: str,
) -> tuple[
    ArtifactRef | None,
    VodArtifactPersistenceIssue | None,
    Literal["not_requested", "persisted", "failed"],
]:
    """Best-effort single-flight copy of a completed subtitle task output."""
    if task.output_url is None or not persist_output:
        return None, None, "not_requested"

    runtime = get_runtime(ctx)
    async with runtime.task_artifact_locks.acquire("vod-mediakit", task_id) as singleflight:
        if singleflight.artifacts and singleflight.artifacts.get("video") is not None:
            return singleflight.artifacts["video"], None, "persisted"

        try:
            cached = await runtime.task_artifact_cache.get("vod-mediakit", task_id)
            cached_video = cached.get("video") if cached else None
        except Exception:
            cached_video = None
            await context_log(ctx, "warning", f"VOD {label} artifact cache lookup failed.")
        if cached_video is not None:
            singleflight.artifacts = {"video": cached_video}
            return cached_video, None, "persisted"

        try:
            video_ref = await runtime.artifact_store.copy_from_trusted_url(
                url=str(task.output_url),
                media_type=MediaType.VIDEO,
                mime_type="video/mp4",
                source_expires_at=task.source_expires_at,
                auth=owner,
            )
        except ArtifactPersistenceError as exc:
            await context_log(
                ctx, "warning", f"VOD {label} output persistence failed: {exc.safe_message}"
            )
            return (
                None,
                VodArtifactPersistenceIssue(
                    code=exc.code,
                    message=exc.safe_message,
                    retryable=exc.retryable,
                    artifact_limit_bytes=get_media_limits().video_max_bytes,
                ),
                "failed",
            )
        except Exception:
            await context_log(
                ctx,
                "warning",
                f"VOD {label} output persistence failed due to an internal storage error.",
            )
            return (
                None,
                VodArtifactPersistenceIssue(
                    code="storage_failed",
                    message="Provider output could not be written to artifact storage.",
                    retryable=True,
                    artifact_limit_bytes=get_media_limits().video_max_bytes,
                ),
                "failed",
            )

        singleflight.artifacts = {"video": video_ref}
        try:
            await runtime.task_artifact_cache.set("vod-mediakit", task_id, {"video": video_ref})
        except Exception:
            await context_log(
                ctx,
                "warning",
                f"VOD {label} artifact cache update failed; artifact remains available.",
            )
        return video_ref, None, "persisted"


async def poll_subtitle_task[OutputT: VodSubtitleTaskOutput](
    *,
    input_task_id: str,
    persist_output: bool,
    ctx: Context,
    service: SubtitleTaskService,
    output_type: type[OutputT],
    label: str,
    log_event: str,
) -> OutputT | ToolResult:
    """Poll, normalize, and optionally persist one subtitle operation task."""
    await context_log(ctx, "info", f"Retrieving VOD AI MediaKit {label} task {input_task_id}")
    await ctx.report_progress(progress=20, total=100)
    runtime = get_runtime(ctx)
    owner = get_principal(ctx)
    await runtime.ownership_store.require_owner("vod-mediakit", input_task_id, owner)

    try:
        task = await call_with_retry(lambda: service.get(input_task_id))
    except ProviderError as exc:
        await context_log(ctx, "error", f"Failed to retrieve {label} task: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=60, total=100)
    common = {
        "task_id": task.task_id,
        "provider_status": task.provider_status,
        "request_id": task.request_id,
        "created_at": task.created_at,
        "finished_at": task.finished_at,
    }
    if task.status == "succeeded":
        video_ref, issue, persistence = await persist_subtitle_output(
            ctx,
            owner,
            input_task_id,
            task,
            persist_output,
            label=label,
        )
        log_info(log_event, task_id=task.task_id, status="succeeded", persistence=persistence)
        return output_type.model_validate(
            {
                **common,
                "status": "succeeded",
                "duration_seconds": task.duration_seconds,
                "resolution": task.resolution,
                "video": video_ref,
                "source_url": task.output_url,
                "source_expires_at": task.source_expires_at,
                "persistence": persistence,
                "persistence_issue": issue,
            }
        )
    if task.status == "failed":
        log_info(log_event, task_id=task.task_id, status="failed", failure_code=task.failure_code)
        return output_type.model_validate(
            {
                **common,
                "status": "failed",
                "persistence": "not_applicable",
                "error": VodSubtitleTaskFailure(
                    code=task.failure_code,
                    message=task.failure_message or f"MediaKit reported the {label} task failed.",
                ),
            }
        )
    log_info(log_event, task_id=task.task_id, status="processing")
    return output_type.model_validate(
        {**common, "status": "processing", "persistence": "not_applicable"}
    )
