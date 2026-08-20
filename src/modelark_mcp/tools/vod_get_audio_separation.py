"""``vod_get_audio_separation`` tool — poll a BytePlus VOD AI MediaKit separate-voice task.

On the first successful poll of a completed task, copies each expiring provider
track URL into ``ArtifactStore`` and caches the artifacts by task ID so repeated
polls do not download twice.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import AnyUrl, BaseModel, Field, UrlConstraints, model_validator

from modelark_mcp.artifacts.store import ArtifactPersistenceError
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.vod_mediakit.separate_voice import (
    VodMediaKitSeparateVoiceService,
)
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.security.auth_context import PrincipalContext
from modelark_mcp.security.media_policy import get_media_limits
from modelark_mcp.tools._errors import provider_error_result
from modelark_mcp.tools._vod_shared import VodArtifactPersistenceIssue

HttpsUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=["https"])]

_TRACK_MIME_TYPE = "audio/aac"


class VodGetAudioSeparationInput(BaseModel):
    """Input for ``vod_get_audio_separation``."""

    task_id: str = Field(description="Task ID returned by vod_separate_audio.")
    persist_output: bool = Field(
        default=True,
        description="Whether to copy completed track URLs into durable artifact storage on first successful poll.",
    )


class VodAudioSeparationFailure(BaseModel):
    """Safe provider failure detail for a failed separation task."""

    code: str | None = Field(default=None, description="Provider failure code, when returned.")
    message: str = Field(
        description="Safe provider failure explanation without credentials or signed URLs."
    )


class VodAudioTrack(BaseModel):
    """A separated audio track's durable artifact and expiring source URL."""

    artifact: ArtifactRef | None = Field(
        default=None,
        description="Durable audio artifact when best-effort persistence succeeds.",
    )
    source_url: HttpsUrl | None = Field(
        default=None,
        description="Expiring provider output URL for the track; preserved even when durable persistence is skipped or fails.",
    )
    source_expires_at: str | None = Field(
        default=None,
        description="ISO-8601 expiry for source_url, normalized from the provider's expires_at.",
    )
    persistence: Literal["not_applicable", "not_requested", "persisted", "failed"] = Field(
        description="Outcome of durable artifact persistence, independent of provider success."
    )
    persistence_issue: VodArtifactPersistenceIssue | None = Field(
        default=None,
        description="Safe explanation when a track could not be persisted durably.",
    )

    @model_validator(mode="after")
    def _validate_state(self) -> VodAudioTrack:
        if self.persistence == "not_requested":
            if self.artifact is not None or self.persistence_issue is not None:
                raise ValueError("not_requested persistence forbids artifact and persistence issue")
        elif self.persistence == "persisted":
            if self.artifact is None or self.persistence_issue is not None:
                raise ValueError(
                    "persisted output requires artifact and forbids a persistence issue"
                )
        elif self.persistence == "failed" and self.persistence_issue is None:
            raise ValueError("failed persistence requires a persistence issue")
        return self


class VodAudioSeparationTaskOutput(BaseModel):
    """Normalized status and separated outputs of a MediaKit separate-voice task."""

    provider: Literal["byteplus-vod-mediakit"] = Field(
        default="byteplus-vod-mediakit", description="Provider surface that processed the request."
    )
    task_id: str = Field(description="Provider task ID.")
    status: Literal["processing", "succeeded", "failed"] = Field(
        description="Normalized separation state: processing until the provider reports completed, then succeeded or failed."
    )
    provider_status: str | None = Field(
        default=None, description="Raw provider status label, when returned."
    )
    request_id: str | None = Field(
        default=None, description="Provider diagnostic request ID, when returned."
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Duration of the input file in seconds, when reported by the completed result.",
    )
    created_at: str | None = Field(
        default=None,
        description="ISO-8601 task creation time normalized from the provider response.",
    )
    finished_at: str | None = Field(
        default=None,
        description="ISO-8601 task completion time normalized from the provider response.",
    )
    voice: VodAudioTrack | None = Field(
        default=None, description="Separated vocal audio track, on success."
    )
    background: VodAudioTrack | None = Field(
        default=None, description="Separated background audio track, on success."
    )
    music: VodAudioTrack | None = Field(
        default=None, description="Separated music track (Drama/Narrate scenes), on success."
    )
    sfx: VodAudioTrack | None = Field(
        default=None,
        description="Separated sound-effects track (Drama/Narrate scenes), on success.",
    )
    error: VodAudioSeparationFailure | None = Field(
        default=None, description="Provider failure code and safe message for a failed task."
    )

    @model_validator(mode="after")
    def _validate_state(self) -> VodAudioSeparationTaskOutput:
        tracks = (self.voice, self.background, self.music, self.sfx)
        if self.status == "processing":
            if any(track is not None for track in tracks):
                raise ValueError("processing output must not carry audio tracks")
            if self.duration_seconds is not None:
                raise ValueError("processing output must not carry a duration")
            if self.error is not None:
                raise ValueError("processing output must not carry a provider failure")
        elif self.status == "succeeded":
            if all(track is None for track in tracks):
                raise ValueError("succeeded output requires at least one audio track")
            for track in tracks:
                if track is not None and track.source_url is None:
                    raise ValueError("succeeded audio tracks require source_url")
            if self.error is not None:
                raise ValueError("succeeded output must not carry a provider failure")
        elif self.error is None:
            raise ValueError("failed output requires provider failure detail")
        return self


_TRACKS = (
    ("voice", "voice_url"),
    ("background", "background_url"),
    ("music", "music_url"),
    ("sfx", "sfx_url"),
)


async def _persist_track(
    ctx: Context,
    owner: PrincipalContext,
    task_id: str,
    track_key: str,
    url: HttpsUrl,
    source_expires_at: str | None,
) -> tuple[
    ArtifactRef | None,
    VodArtifactPersistenceIssue | None,
    Literal["persisted", "failed"],
]:
    """Best-effort copy of one completed track URL into the artifact store."""
    runtime = get_runtime(ctx)
    cache = await runtime.task_artifact_cache.get("vod-mediakit", task_id)
    existing = (cache or {}).get(track_key)
    if existing is not None:
        return existing, None, "persisted"

    try:
        ref = await runtime.artifact_store.copy_from_trusted_url(
            url=str(url),
            media_type=MediaType.AUDIO,
            mime_type=_TRACK_MIME_TYPE,
            source_expires_at=source_expires_at,
            auth=owner,
        )
    except ArtifactPersistenceError as exc:
        issue = VodArtifactPersistenceIssue(
            code=exc.code,
            message=exc.safe_message,
            retryable=exc.retryable,
            artifact_limit_bytes=get_media_limits().audio_max_bytes,
        )
        await ctx.warning(f"VOD audio separation persistence failed: {exc.safe_message}")
        return None, issue, "failed"
    except Exception:
        issue = VodArtifactPersistenceIssue(
            code="storage_failed",
            message="Provider output could not be written to artifact storage.",
            retryable=True,
            artifact_limit_bytes=get_media_limits().audio_max_bytes,
        )
        await ctx.warning(
            "VOD audio separation persistence failed due to an internal storage error."
        )
        return None, issue, "failed"

    updated = dict(cache or {})
    updated[track_key] = ref
    await runtime.task_artifact_cache.set("vod-mediakit", task_id, updated)
    return ref, None, "persisted"


async def vod_get_audio_separation(
    input: VodGetAudioSeparationInput, ctx: Context
) -> VodAudioSeparationTaskOutput | ToolResult:
    """Poll the status and output of a BytePlus VOD AI MediaKit separate-voice task.

    On the first successful poll with ``persist_output=True``, copies each
    expiring provider track URL into durable artifact storage. Subsequent calls
    return the cached artifact references without re-downloading.
    """
    await ctx.info(f"Retrieving VOD AI MediaKit audio separation task {input.task_id}")
    await ctx.report_progress(progress=20, total=100)
    runtime = get_runtime(ctx)
    owner = get_principal(ctx)
    await runtime.ownership_store.require_owner("vod-mediakit", input.task_id, owner)

    service = VodMediaKitSeparateVoiceService()
    try:
        task = await call_with_retry(lambda: service.get(input.task_id))
    except ProviderError as exc:
        await ctx.error(f"Failed to retrieve audio separation task: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=60, total=100)

    if task.status == "succeeded":
        track_outputs: dict[str, VodAudioTrack | None] = {}
        for track_key, url_attr in _TRACKS:
            url = getattr(task, url_attr)
            if url is None:
                track_outputs[track_key] = None
                continue
            if not input.persist_output:
                track_outputs[track_key] = VodAudioTrack(
                    source_url=url,
                    source_expires_at=task.source_expires_at,
                    persistence="not_requested",
                )
                continue
            ref, issue, persistence = await _persist_track(
                ctx, owner, input.task_id, track_key, url, task.source_expires_at
            )
            track_outputs[track_key] = VodAudioTrack(
                artifact=ref,
                source_url=url,
                source_expires_at=task.source_expires_at,
                persistence=persistence,
                persistence_issue=issue,
            )
        return VodAudioSeparationTaskOutput(
            provider="byteplus-vod-mediakit",
            task_id=task.task_id,
            status="succeeded",
            provider_status=task.provider_status,
            request_id=task.request_id,
            duration_seconds=task.duration_seconds,
            created_at=task.created_at,
            finished_at=task.finished_at,
            voice=track_outputs["voice"],
            background=track_outputs["background"],
            music=track_outputs["music"],
            sfx=track_outputs["sfx"],
        )

    if task.status == "failed":
        return VodAudioSeparationTaskOutput(
            provider="byteplus-vod-mediakit",
            task_id=task.task_id,
            status="failed",
            provider_status=task.provider_status,
            request_id=task.request_id,
            created_at=task.created_at,
            finished_at=task.finished_at,
            error=VodAudioSeparationFailure(
                code=task.failure_code,
                message=task.failure_message or "MediaKit reported the separation task failed.",
            ),
        )

    return VodAudioSeparationTaskOutput(
        provider="byteplus-vod-mediakit",
        task_id=task.task_id,
        status="processing",
        provider_status=task.provider_status,
        request_id=task.request_id,
        created_at=task.created_at,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
