"""Internal request/response DTOs for the VOD AI MediaKit endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    UrlConstraints,
    field_validator,
    model_validator,
)

HttpsUrl = Annotated[AnyUrl, UrlConstraints(allowed_schemes=["https"])]


class VodMediaKitEnhancementRequest(BaseModel):
    """Exact request profile accepted by ``POST /enhance-video``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    video_url: HttpsUrl
    scene: Literal["common"] = "common"
    tool_version: Literal["professional"] = "professional"
    resolution: Literal["4k"] = "4k"
    bitrate_level: Literal["high"] = "high"
    fps: Literal[24] = 24
    project: str = Field(
        default="default",
        min_length=1,
        max_length=128,
        serialization_alias="Project",
    )


class VodMediaKitProviderErrorDetail(BaseModel):
    """Error detail returned by MediaKit."""

    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    type: str | None = None
    message: str | None = None


class VodMediaKitProviderResult(BaseModel):
    """Provisional synchronous result object from MediaKit."""

    model_config = ConfigDict(extra="ignore")

    output_url: HttpsUrl = Field(validation_alias=AliasChoices("output_url", "video_url", "url"))
    request_id: str | None = None
    task_id: str | None = Field(default=None, validation_alias=AliasChoices("task_id", "id"))
    status: str | None = None
    mime_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("mime_type", "content_type"),
    )
    expires_at: str | None = Field(
        default=None,
        validation_alias=AliasChoices("expires_at", "expiration"),
    )
    output_size_bytes: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("output_size_bytes", "size"),
    )
    error: VodMediaKitProviderErrorDetail | None = None

    @field_validator("expires_at")
    @classmethod
    def require_iso_8601_expiry(cls, value: str | None) -> str | None:
        """Accept expiry metadata only when it is an ISO-8601 timestamp."""
        if value is not None:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class VodMediaKitProviderResponse(BaseModel):
    """Supported provisional synchronous success envelope."""

    model_config = ConfigDict(extra="ignore")

    success: Literal[True]
    result: VodMediaKitProviderResult = Field(validation_alias=AliasChoices("data", "result"))
    request_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def require_exactly_one_result_container(cls, value: Any) -> Any:
        """Reject ambiguous envelopes containing both result aliases."""
        if isinstance(value, dict) and "data" in value and "result" in value:
            raise ValueError("response must contain only one of 'data' or 'result'")
        return value


class VodMediaKitAcceptedResponse(BaseModel):
    """Directly observed asynchronous acceptance envelope."""

    model_config = ConfigDict(extra="ignore")

    success: Literal[True]
    task_id: str = Field(min_length=1)
    request_id: str | None = None


class EnhancementSubmission(BaseModel):
    """Normalized accepted or completed enhancement result for the tool layer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "succeeded"]
    request_id: str | None = None
    provider_log_id: str | None = None
    task_id: str | None = None
    output_url: HttpsUrl | None = None
    mime_type: str | None = None
    expires_at: str | None = None
    output_size_bytes: int | None = Field(default=None, ge=0)
    provider_status: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> EnhancementSubmission:
        """Require a task for acceptance and an output URL for completion."""
        if self.status == "accepted":
            if not self.task_id:
                raise ValueError("accepted enhancement requires task_id")
            if self.output_url is not None:
                raise ValueError("accepted enhancement must not include output_url")
        elif self.output_url is None:
            raise ValueError("succeeded enhancement requires output_url")
        return self

    @field_validator("provider_status", "failure_code", "failure_message")
    @classmethod
    def reject_blank_optional_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class VodMediaKitProviderErrorResponse(BaseModel):
    """Verified MediaKit error response envelope."""

    model_config = ConfigDict(extra="ignore")

    success: bool | None = None
    error: VodMediaKitProviderErrorDetail | None = None


class VodMediaKitTranscodeVideoOptions(BaseModel):
    """Verified ``video`` object for ``POST /transcode-video``.

    Field names, enum values, and ranges are confirmed from the official AI
    MediaKit API reference (2026-08-14).
    """

    model_config = ConfigDict(extra="forbid")

    codec: Literal["h264", "h265"] = Field(
        default="h264",
        description="Output video codec.",
    )
    scale_type: Literal[0, 1, 2] = Field(
        default=2,
        description="Scaling mode: 0 = follow source, 1 = long/short-side limit, 2 = width/height limit.",
    )
    scale_mode: Literal[0, 1, 2] = Field(
        default=2,
        description="Aspect handling when scaling: 0 = no upsampling, 1 = stretch, 2 = letterbox.",
    )
    scale_width: int | None = Field(
        default=None,
        ge=0,
        le=4320,
        description="Target width in pixels; only when scale_type=2.",
    )
    scale_height: int | None = Field(
        default=None,
        ge=0,
        le=4320,
        description="Target height in pixels; only when scale_type=2.",
    )
    scale_short: int | None = Field(
        default=None,
        ge=0,
        le=4320,
        description="Target short side in pixels; only when scale_type=1.",
    )
    scale_long: int | None = Field(
        default=None,
        ge=0,
        le=4320,
        description="Target long side in pixels; only when scale_type=1.",
    )
    bitrate_mode: Literal["crf", "abr", "cbr"] = Field(
        default="crf",
        description="Bitrate control mode: crf, abr, or cbr.",
    )
    bitrate_crf: int = Field(
        default=25,
        ge=0,
        le=51,
        description="CRF quality level; only used when bitrate_mode=crf.",
    )
    bitrate_kbps: int = Field(
        default=2000,
        ge=10,
        le=50000,
        description="Bitrate in kbps.",
    )
    fps_mode: Literal["vfr", "cfr"] = Field(
        default="vfr",
        description="Frame-rate mode; only takes effect after fps is set.",
    )
    fps: int | None = Field(
        default=None,
        ge=1,
        le=240,
        description="Target frame rate; unset keeps the source rate.",
    )
    is_hdr_to_sdr: bool = Field(
        default=True,
        description="Convert HDR input to SDR.",
    )

    @model_validator(mode="after")
    def validate_scale_fields(self) -> VodMediaKitTranscodeVideoOptions:
        if self.scale_type == 2 and self.scale_width is None and self.scale_height is None:
            raise ValueError("scale_type=2 requires scale_width and/or scale_height")
        if self.scale_type == 1 and self.scale_short is None and self.scale_long is None:
            raise ValueError("scale_type=1 requires scale_short and/or scale_long")
        if self.scale_type != 2 and (self.scale_width is not None or self.scale_height is not None):
            raise ValueError("scale_width/scale_height require scale_type=2")
        if self.scale_type != 1 and (self.scale_short is not None or self.scale_long is not None):
            raise ValueError("scale_short/scale_long require scale_type=1")
        return self


class VodMediaKitTranscodeRequest(BaseModel):
    """Verified request body for ``POST /tools/transcode-video``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    video_url: HttpsUrl
    container_format: Literal["MP4", "FLV", "MPEGTS"] = "MP4"
    video: VodMediaKitTranscodeVideoOptions = Field(
        default_factory=VodMediaKitTranscodeVideoOptions
    )


class VodMediaKitTranscodeTaskResult(BaseModel):
    """Verified ``result`` object of a completed transcode task."""

    model_config = ConfigDict(extra="ignore")

    video_url: HttpsUrl = Field(validation_alias=AliasChoices("video_url", "output_url", "url"))
    duration: float | None = Field(default=None, ge=0)
    resolution: str | None = None
    video_codec: str | None = None


class VodMediaKitTranscodeTaskResponse(BaseModel):
    """Verified polling response from ``GET /tasks/{task_id}``."""

    model_config = ConfigDict(extra="ignore")

    success: Literal[True]
    task_id: str = Field(min_length=1)
    task_type: str | None = None
    status: str = Field(min_length=1)
    result: VodMediaKitTranscodeTaskResult | None = None
    error: VodMediaKitProviderErrorDetail | None = None
    request_id: str | None = None
    queue_id: str | None = None
    expires_at: str | int | None = Field(
        default=None,
        description="Provider output URL expiry as Unix-seconds or ISO-8601.",
    )
    created_at: str | int | None = None
    finished_at: str | int | None = None


class TranscodeSubmission(BaseModel):
    """Normalized accepted transcode submission for the tool layer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"]
    request_id: str | None = None
    provider_log_id: str | None = None
    task_id: str = Field(min_length=1)


class TranscodeTask(BaseModel):
    """Normalized transcode task state for the tool layer."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    status: Literal["processing", "succeeded", "failed"]
    provider_status: str | None = None
    request_id: str | None = None
    output_url: HttpsUrl | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    resolution: str | None = None
    video_codec: str | None = None
    created_at: str | None = None
    finished_at: str | None = None
    source_expires_at: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> TranscodeTask:
        if self.status == "succeeded":
            if self.output_url is None:
                raise ValueError("succeeded transcode task requires output_url")
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("succeeded transcode task must not carry a failure")
        elif self.status == "processing":
            if self.output_url is not None:
                raise ValueError("processing transcode task must not carry output_url")
        elif self.failure_code is None and self.failure_message is None:
            raise ValueError("failed transcode task requires failure detail")
        return self

    @field_validator("failure_code", "failure_message")
    @classmethod
    def reject_blank_optional_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value
