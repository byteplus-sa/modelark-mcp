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
