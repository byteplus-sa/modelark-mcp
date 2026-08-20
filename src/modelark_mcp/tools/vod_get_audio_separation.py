"""``vod_get_audio_separation`` tool — poll a BytePlus VOD AudioExtract task.

Returns the separated vocal and background audio ``FileName`` values (plus
optional playback URLs built from a configured playback domain). Outputs are
stored in the VOD space and are not copied into the local artifact store.
"""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import (
    AnyUrl,
    BaseModel,
    Field,
    UrlConstraints,
    field_validator,
    model_validator,
)

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.vod.audio_separation import VodAudioSeparationService
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.tools._errors import provider_error_result

HttpsUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=["https"])]


def _validate_playback_domain(value: str) -> str:
    """Return a validated bare-hostname playback domain or raise ``ValueError``."""
    value = value.strip()
    if value.startswith(("/", "http://", "https://")) or "@" in value:
        raise ValueError(
            "playback_domain must be a bare hostname without a scheme, path, or credentials."
        )
    if any(ch in value for ch in ("/", "?", "#", ":", " ")):
        raise ValueError(
            "playback_domain must be a bare hostname without a scheme, port, path, query, or fragment."
        )
    labels = value.split(".")
    if any(not label or label.strip() != label for label in labels):
        raise ValueError("playback_domain must be a valid hostname.")
    return value


class VodGetAudioSeparationInput(BaseModel):
    """Input for ``vod_get_audio_separation``."""

    run_id: str = Field(description="RunId returned by vod_separate_audio.")
    playback_domain: str | None = Field(
        default=None,
        description=(
            "Optional bare playback domain (e.g. 'play.example.com') used to build "
            "output audio URLs. Overrides BYTEPLUS_VOD_PLAYBACK_DOMAIN when set."
        ),
    )

    @field_validator("playback_domain")
    @classmethod
    def _validate_playback_domain_field(cls, value: str | None) -> str | None:
        if not value:
            return value
        return _validate_playback_domain(value)


class VodAudioTrack(BaseModel):
    """A separated audio track's storage path, size, and optional public URL."""

    file_name: str = Field(description="Storage path of the separated audio file.")
    size_bytes: int | None = Field(
        default=None, ge=0, description="Size of the separated audio file in bytes."
    )
    url: HttpsUrl | None = Field(
        default=None,
        description="Public HTTPS URL built from the playback domain and FileName, when available.",
    )


class VodAudioSeparationFailure(BaseModel):
    """Safe provider failure detail for a failed separation task."""

    code: str | None = Field(default=None, description="Provider failure code, when returned.")
    message: str = Field(
        description="Safe provider failure explanation without credentials or signed URLs."
    )


class VodAudioSeparationTaskOutput(BaseModel):
    """Normalized status and separated outputs of a BytePlus VOD AudioExtract task."""

    provider: Literal["byteplus-vod"] = Field(
        default="byteplus-vod", description="Provider surface that processed the request."
    )
    run_id: str = Field(description="Provider RunId of the separation task.")
    status: Literal["processing", "succeeded", "failed"] = Field(
        description="Normalized separation state: processing until the provider reports Success, then succeeded or failed."
    )
    provider_status: str | None = Field(
        default=None, description="Raw provider Status label, when returned."
    )
    request_id: str | None = Field(
        default=None, description="Provider diagnostic request ID, when returned."
    )
    duration_seconds: float | None = Field(
        default=None, ge=0, description="Duration of the input file in seconds."
    )
    voice: VodAudioTrack | None = Field(
        default=None, description="Separated vocal audio track, on success."
    )
    background: VodAudioTrack | None = Field(
        default=None, description="Separated background audio track, on success."
    )
    error: VodAudioSeparationFailure | None = Field(
        default=None, description="Provider failure code and safe message for a failed task."
    )

    @model_validator(mode="after")
    def _validate_state(self) -> VodAudioSeparationTaskOutput:
        if self.status == "processing":
            if self.voice is not None or self.background is not None:
                raise ValueError("processing output must not carry audio tracks")
            if self.duration_seconds is not None:
                raise ValueError("processing output must not carry a duration")
            if self.error is not None:
                raise ValueError("processing output must not carry a provider failure")
        elif self.status == "succeeded":
            if self.voice is None:
                raise ValueError("succeeded output requires the voice track")
            if self.error is not None:
                raise ValueError("succeeded output must not carry a provider failure")
        elif self.error is None:
            raise ValueError("failed output requires provider failure detail")
        return self


def _build_track_url(domain: str | None, file_name: str) -> HttpsUrl | None:
    """Build ``https://{domain}/{file_name}`` when the domain is a safe bare hostname."""
    if not domain:
        return None
    domain = _validate_playback_domain(domain)
    path = quote(file_name, safe="/")
    return HttpsUrl(f"https://{domain}/{path}")


async def vod_get_audio_separation(
    input: VodGetAudioSeparationInput, ctx: Context
) -> VodAudioSeparationTaskOutput | ToolResult:
    """Poll the status and output of a BytePlus VOD voice and background audio separation task.

    Returns the separated vocal and background audio storage paths (FileName),
    sizes, and optional public URLs when a playback domain is supplied or
    configured. Outputs remain in the VOD space; this tool does not copy them
    into durable local artifact storage.
    """
    await ctx.info(f"Retrieving VOD audio separation task {input.run_id}")
    await ctx.report_progress(progress=20, total=100)
    runtime = get_runtime(ctx)
    owner = get_principal(ctx)
    await runtime.ownership_store.require_owner("vod", input.run_id, owner)

    domain = input.playback_domain or runtime.settings.vod_playback_domain or None

    service = VodAudioSeparationService()
    try:
        task = await call_with_retry(lambda: service.get(input.run_id))
    except ProviderError as exc:
        await ctx.error(f"Failed to retrieve audio separation task: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=60, total=100)

    if task.status == "succeeded":
        voice = VodAudioTrack(
            file_name=task.voice_file_name or "",
            size_bytes=task.voice_size_bytes,
            url=_build_track_url(domain, task.voice_file_name or ""),
        )
        background = None
        if task.background_file_name:
            background = VodAudioTrack(
                file_name=task.background_file_name,
                size_bytes=task.background_size_bytes,
                url=_build_track_url(domain, task.background_file_name),
            )
        return VodAudioSeparationTaskOutput(
            provider="byteplus-vod",
            run_id=task.run_id,
            status="succeeded",
            provider_status=task.provider_status,
            request_id=task.request_id,
            duration_seconds=task.duration_seconds,
            voice=voice,
            background=background,
        )

    if task.status == "failed":
        return VodAudioSeparationTaskOutput(
            provider="byteplus-vod",
            run_id=task.run_id,
            status="failed",
            provider_status=task.provider_status,
            request_id=task.request_id,
            error=VodAudioSeparationFailure(
                code=task.failure_code,
                message=task.failure_message or "VOD OpenAPI reported the separation task failed.",
            ),
        )

    return VodAudioSeparationTaskOutput(
        provider="byteplus-vod",
        run_id=task.run_id,
        status="processing",
        provider_status=task.provider_status,
        request_id=task.request_id,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
