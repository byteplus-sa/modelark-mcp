"""MCP tool for the BytePlus VOD AI MediaKit enhancement profile.

Implements ``plans/PLAN_BYTEPLUS_VOD_AI_MEDIAKIT_VIDEO_ENHANCEMENT.md``.
The upstream success schema remains provisional and is isolated in the
provider adapter; this tool exposes a stable, bounded persistence outcome.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import AnyUrl, BaseModel, Field, UrlConstraints

from modelark_mcp.artifacts.store import ArtifactPersistenceError
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.vod_mediakit.enhancement import VodMediaKitEnhancementService
from modelark_mcp.providers.vod_mediakit.schemas import VodMediaKitEnhancementRequest
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.security.media_policy import get_media_limits
from modelark_mcp.security.url_policy import validate_url
from modelark_mcp.tools._errors import provider_error_result

HttpsUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=["https"])]


class VodEnhanceVideoInput(BaseModel):
    """Input for the exact currently verified MediaKit enhancement profile."""

    video_url: HttpsUrl = Field(
        description="Public HTTPS source-video URL that BytePlus can fetch. Private and link-local destinations are rejected."
    )
    scene: Literal["common"] = Field(
        default="common", description="Current MediaKit scene profile; only 'common' is verified."
    )
    tool_version: Literal["professional"] = Field(
        default="professional",
        description="Current enhancement profile; only 'professional' is verified.",
    )
    resolution: Literal["4k"] = Field(
        default="4k", description="Current target resolution; only '4k' is verified."
    )
    bitrate_level: Literal["high"] = Field(
        default="high", description="Current target bitrate profile; only 'high' is verified."
    )
    fps: Literal[24] = Field(
        default=24,
        description="Current target frame rate in frames per second; only 24 is verified.",
    )
    project: str = Field(
        default="default",
        min_length=1,
        max_length=128,
        description="MediaKit project label, serialized upstream using the case-sensitive 'Project' field.",
    )
    input_duration_seconds: float | None = Field(
        default=None,
        gt=0,
        description="Optional source duration in seconds. Retained for future pricing support; no estimate is emitted until convenience-endpoint billing is confirmed.",
    )
    persist: bool = Field(
        default=True,
        description="Best-effort copy of the completed output into the durable MCP artifact store.",
    )


class VodArtifactPersistenceIssue(BaseModel):
    """Safe explanation for a provider success that was not persisted."""

    code: Literal[
        "untrusted_output_host",
        "output_too_large",
        "invalid_output_mime",
        "source_expired",
        "download_failed",
        "storage_failed",
    ] = Field(description="Stable persistence failure category.")
    message: str = Field(description="Credential- and URL-safe persistence failure message.")
    retryable: bool = Field(description="Whether persistence may succeed if attempted again later.")
    artifact_limit_bytes: int = Field(
        description="Maximum video size accepted by the durable artifact policy, in bytes."
    )


class VodEnhanceVideoOutput(BaseModel):
    """Normalized successful MediaKit enhancement result."""

    provider: Literal["byteplus-vod-mediakit"] = Field(
        default="byteplus-vod-mediakit", description="Provider surface that enhanced the video."
    )
    status: Literal["accepted", "succeeded"] = Field(
        description="Normalized state: accepted for an asynchronous task or succeeded for a completed output.",
    )
    request_id: str | None = Field(
        default=None, description="Provider diagnostic request ID, when returned."
    )
    provider_log_id: str | None = Field(
        default=None, description="Provider x-tt-logid diagnostic identifier, when returned."
    )
    task_id: str | None = Field(
        default=None,
        description="Provider task identifier, when included in the synchronous result.",
    )
    provider_status: str | None = Field(
        default=None,
        description="Raw provider status label, when included in the accepted success response.",
    )
    video: ArtifactRef | None = Field(
        default=None,
        description="Durable enhanced-video artifact when best-effort persistence succeeds.",
    )
    source_url: HttpsUrl | None = Field(
        default=None,
        description="Provider output URL for succeeded results; absent while an accepted task is processing.",
    )
    source_expires_at: str | None = Field(
        default=None, description="Provider-reported ISO-8601 output URL expiry, when returned."
    )
    output_size_bytes: int | None = Field(
        default=None, ge=0, description="Provider-reported output size in bytes, when returned."
    )
    persistence: Literal["not_applicable", "not_requested", "persisted", "failed"] = Field(
        description="Outcome of durable artifact persistence, independent of provider success."
    )
    persistence_issue: VodArtifactPersistenceIssue | None = Field(
        default=None, description="Safe failure details when persistence did not complete."
    )
    estimated_cost_usd: float | None = Field(
        default=None,
        description="Always null until convenience-endpoint pricing and billing-unit mapping are confirmed.",
    )


async def vod_enhance_video(
    input: VodEnhanceVideoInput, ctx: Context
) -> VodEnhanceVideoOutput | ToolResult:
    """Enhance a public video using BytePlus VOD AI MediaKit.

    Submits the exact common/professional/4K/high/24-fps profile. The mutation
    is never retried automatically because completion can be ambiguous after a
    timeout. A successful provider URL is always returned; durable persistence
    is best-effort and remains limited to the configured 200 MiB video policy.
    """
    runtime = get_runtime(ctx)
    settings = runtime.settings
    if not settings.has_vod_mediakit:
        raise ValueError(
            "BYTEPLUS_VOD_MEDIAKIT_API_KEY is not configured. Set it to enable this tool."
        )

    validated_source = validate_url(str(input.video_url))
    request = VodMediaKitEnhancementRequest.model_validate(
        {
            "video_url": validated_source.url,
            "scene": input.scene,
            "tool_version": input.tool_version,
            "resolution": input.resolution,
            "bitrate_level": input.bitrate_level,
            "fps": input.fps,
            "project": input.project,
        }
    )
    owner = get_principal(ctx)
    service = VodMediaKitEnhancementService()
    await ctx.info("Starting VOD AI MediaKit enhancement")
    await ctx.report_progress(progress=20, total=100)
    try:
        async with runtime.provider_limiters.acquire("vod-mediakit", owner):
            submission = await service.enhance(request)
    except ProviderError as exc:
        await ctx.error(f"VOD AI MediaKit enhancement failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=75, total=100)
    if submission.status == "accepted":
        assert submission.task_id is not None
        await runtime.ownership_store.record("vod-mediakit", submission.task_id, owner)
        await ctx.report_progress(progress=100, total=100)
        return VodEnhanceVideoOutput(
            status="accepted",
            request_id=submission.request_id,
            provider_log_id=submission.provider_log_id,
            task_id=submission.task_id,
            provider_status=submission.provider_status,
            persistence="not_applicable",
        )

    assert submission.output_url is not None
    artifact: ArtifactRef | None = None
    issue: VodArtifactPersistenceIssue | None = None
    persistence: Literal["not_requested", "persisted", "failed"] = "not_requested"
    if input.persist:
        try:
            artifact = await runtime.artifact_store.copy_from_trusted_url(
                url=str(submission.output_url),
                media_type=MediaType.VIDEO,
                mime_type=submission.mime_type or "video/mp4",
                source_expires_at=submission.expires_at,
                auth=owner,
            )
            persistence = "persisted"
        except ArtifactPersistenceError as exc:
            persistence = "failed"
            issue = VodArtifactPersistenceIssue(
                code=exc.code,
                message=exc.safe_message,
                retryable=exc.retryable,
                artifact_limit_bytes=get_media_limits().video_max_bytes,
            )
            await ctx.warning(f"VOD output persistence failed: {exc.safe_message}")
        except Exception:
            # Provider success may already be billable. Preserve its source URL even
            # when a future/custom artifact backend violates the typed error contract.
            persistence = "failed"
            issue = VodArtifactPersistenceIssue(
                code="storage_failed",
                message="Provider output could not be written to artifact storage.",
                retryable=True,
                artifact_limit_bytes=get_media_limits().video_max_bytes,
            )
            await ctx.warning("VOD output persistence failed due to an internal storage error.")

    await ctx.report_progress(progress=100, total=100)
    return VodEnhanceVideoOutput(
        status="succeeded",
        request_id=submission.request_id,
        provider_log_id=submission.provider_log_id,
        task_id=submission.task_id,
        provider_status=submission.provider_status,
        video=artifact,
        source_url=submission.output_url,
        source_expires_at=submission.expires_at,
        output_size_bytes=submission.output_size_bytes,
        persistence=persistence,
        persistence_issue=issue,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
