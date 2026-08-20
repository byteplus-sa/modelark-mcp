"""Internal request/response DTOs for the BytePlus VOD OpenAPI AudioExtract surface.

Wire-level field names use PascalCase (``FileName``, ``AudioExtract``,
``RunId``), so every model applies a PascalCase alias generator. Outbound
request DTOs forbid extra fields; inbound response DTOs ignore extra fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _pascal_alias(field_name: str) -> str:
    """Convert ``snake_case`` field names to the OpenAPI's ``PascalCase`` JSON keys."""
    return "".join(part.capitalize() for part in field_name.split("_"))


class VodAudioExtractAudioOption(BaseModel):
    """Audio output option for an ``AudioExtract`` task."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    format: Literal["aac"] = Field(default="aac")


class VodAudioExtractTask(BaseModel):
    """The ``AudioExtract`` task parameters."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    voice: bool = Field(default=True)
    audio_option: VodAudioExtractAudioOption = Field(
        default_factory=VodAudioExtractAudioOption,
    )


class VodTaskSpec(BaseModel):
    """The ``Operation.Task`` envelope for an AudioExtract submission."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    type: Literal["AudioExtract"] = "AudioExtract"
    audio_extract: VodAudioExtractTask = Field(default_factory=VodAudioExtractTask)


class VodOperationSpec(BaseModel):
    """The ``Operation`` envelope for a single-task submission."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    type: Literal["Task"] = "Task"
    task: VodTaskSpec = Field(default_factory=VodTaskSpec)


class VodDirectUrlInput(BaseModel):
    """DirectUrl storage-path reference for a file in the VOD space's TOS bucket."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    file_name: str = Field(min_length=1, max_length=2048)
    space_name: str | None = Field(default=None, min_length=1, max_length=128)
    bucket_name: str | None = Field(default=None, min_length=1, max_length=256)


class VodInputSpec(BaseModel):
    """The ``Input`` envelope for a DirectUrl submission."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    type: Literal["DirectUrl"] = "DirectUrl"
    direct_url: VodDirectUrlInput


class VodStartExecutionRequest(BaseModel):
    """Request body for ``POST /?Action=StartExecution``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=_pascal_alias)

    input: VodInputSpec
    operation: VodOperationSpec = Field(default_factory=VodOperationSpec)


class VodErrorDetail(BaseModel):
    """OpenAPI error detail nested under ``ResponseMetadata``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    code: str | None = None
    code_n: int | None = None
    message: str | None = None

    @property
    def effective_code(self) -> str | None:
        """Return the string code when present, else the numeric code."""
        if self.code:
            return self.code
        if self.code_n is not None:
            return str(self.code_n)
        return None


class VodResponseMetadata(BaseModel):
    """Common ``ResponseMetadata`` envelope."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    request_id: str | None = None
    action: str | None = None
    version: str | None = None
    region: str | None = None
    service: str | None = None
    error: VodErrorDetail | None = None


class VodStartExecutionResult(BaseModel):
    """``Result`` of a successful StartExecution call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    run_id: str = Field(min_length=1)


class VodStartExecutionResponse(BaseModel):
    """Raw StartExecution response envelope."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    response_metadata: VodResponseMetadata | None = None
    result: VodStartExecutionResult | None = None


class VodAudioFileInfo(BaseModel):
    """A separated audio file's ``FileName`` and ``Size``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    file_name: str | None = None
    size: int | None = None

    @field_validator("size", mode="before")
    @classmethod
    def normalize_size(cls, value: Any) -> int | None:
        """Coerce numeric or numeric-string byte counts to ``int``."""
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("size must be a byte count")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.isdigit():
                return int(stripped)
        raise ValueError("size must be a numeric byte count")


class VodAudioExtractOutput(BaseModel):
    """The ``Output.Task.AudioExtract`` result object."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    duration: float | None = Field(default=None, ge=0)
    voice: VodAudioFileInfo | None = None
    background: VodAudioFileInfo | None = None


class VodOutputTask(BaseModel):
    """The ``Output.Task`` result object."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    type: str | None = None
    audio_extract: VodAudioExtractOutput | None = None


class VodOutputSpec(BaseModel):
    """The ``Output`` result envelope."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    type: str | None = None
    task: VodOutputTask | None = None


class VodGetExecutionResult(BaseModel):
    """``Result`` of a GetExecution call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    run_id: str | None = None
    status: str | None = None
    code: str | None = None
    output: VodOutputSpec | None = None


class VodGetExecutionResponse(BaseModel):
    """Raw GetExecution response envelope."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, alias_generator=_pascal_alias)

    response_metadata: VodResponseMetadata | None = None
    result: VodGetExecutionResult | None = None


class AudioSeparationSubmission(BaseModel):
    """Normalized accepted separation submission for the tool layer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted"] = "accepted"
    request_id: str | None = None
    run_id: str = Field(min_length=1)


class AudioSeparationTask(BaseModel):
    """Normalized separation task state for the tool layer."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    status: Literal["processing", "succeeded", "failed"]
    provider_status: str | None = None
    request_id: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    voice_file_name: str | None = None
    voice_size_bytes: int | None = Field(default=None, ge=0)
    background_file_name: str | None = None
    background_size_bytes: int | None = Field(default=None, ge=0)
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> AudioSeparationTask:
        if self.status == "succeeded":
            if not self.voice_file_name:
                raise ValueError("succeeded separation requires voice_file_name")
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("succeeded separation must not carry a failure")
        elif self.status == "processing":
            if self.voice_file_name is not None or self.background_file_name is not None:
                raise ValueError("processing separation must not carry output files")
            if self.duration_seconds is not None:
                raise ValueError("processing separation must not carry a duration")
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("processing separation must not carry a failure")
        elif self.failure_code is None and self.failure_message is None:
            raise ValueError("failed separation requires failure detail")
        return self

    @field_validator("provider_status", "failure_code", "failure_message")
    @classmethod
    def reject_blank_optional_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value
