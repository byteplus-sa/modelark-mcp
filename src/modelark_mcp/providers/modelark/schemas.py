"""ModelArk provider request/response schemas (Seedream + Seedance).

These DTOs model the raw JSON the ModelArk API expects and returns. They
are internal to the provider layer — tool inputs and domain outputs use
separate Pydantic models so vendor field changes do not leak through.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Seedream image generation
# ---------------------------------------------------------------------------


class SeedreamProviderRequest(BaseModel):
    """Raw request body for ``POST /images/generations``."""

    model: str
    prompt: str
    image: str | list[str] | None = None
    size: str | None = None
    seed: int | None = None
    sequential_image_generation: str | None = None
    sequential_image_generation_options: dict[str, Any] | None = None
    stream: bool = False
    output_format: str | None = None
    response_format: str | None = None
    watermark: bool | None = None
    optimize_prompt_options: dict[str, str] | None = None


class SeedreamImageData(BaseModel):
    """Single image item in a Seedream generation response."""

    url: str | None = None
    b64_json: str | None = None
    index: int | None = None
    revised_prompt: str | None = None


class SeedreamProviderResponse(BaseModel):
    """Raw response from ``POST /images/generations``."""

    created: int | None = None
    data: list[SeedreamImageData] = Field(default_factory=list)
    usage: dict[str, Any] | None = None


class SeedreamItemErrorData(BaseModel):
    """Error for a single failed image in a Seedream batch."""

    index: int | None = None
    code: str | None = None
    message: str = ""


class SeedreamProviderErrorResponse(BaseModel):
    """Error response shape from the Seedream API."""

    error: SeedreamItemErrorData = Field(default_factory=SeedreamItemErrorData)


# ---------------------------------------------------------------------------
# Seedance video task API
# ---------------------------------------------------------------------------


class SeedanceContentItem(BaseModel):
    """Content item for the Seedance task creation request."""

    type: str = Field(..., description="text, image_url, video_url, or audio_url")
    text: str | None = None
    image_url: dict[str, str] | str | None = None
    video_url: dict[str, str] | str | None = None
    audio_url: dict[str, str] | str | None = None
    role: str | None = None


class SeedanceCreateProviderRequest(BaseModel):
    """Raw request body for ``POST /contents/generations/tasks``."""

    model: str
    content: list[SeedanceContentItem] = Field(default_factory=list)
    resolution: str | None = None
    ratio: str | None = None
    duration: int | None = None
    seed: int | None = None
    camera_fixed: bool | None = None
    watermark: bool | None = None
    generate_audio: bool | None = None
    return_last_frame: bool | None = None
    service_tier: str | None = None
    execution_expires_after: int | None = None
    priority: int | None = None
    safety_identifier: str | None = None
    callback_url: str | None = None


class SeedanceCreateProviderResponse(BaseModel):
    """Response from ``POST /contents/generations/tasks``."""

    id: str


class SeedanceVideoUrl(BaseModel):
    """Video output in a Seedance task response."""

    url: str
    duration: str | None = None


class SeedanceGenerationUsage(BaseModel):
    """Usage data in a Seedance task response."""

    completion_tokens: int | None = None
    prompt_tokens: int | None = None


class SeedanceGenerationConfig(BaseModel):
    """Generation config echoed in a Seedance task response."""

    resolution: str | None = None
    ratio: str | None = None
    duration: int | str | None = None
    seed: int | None = None
    camera_fixed: bool | None = None
    watermark: bool | None = None
    generate_audio: bool | None = None
    return_last_frame: bool | None = None
    service_tier: str | None = None
    execution_expires_after: int | None = None
    priority: int | None = None
    safety_identifier: str | None = None


class SeedanceErrorDetail(BaseModel):
    """Error detail in a Seedance task response."""

    code: str = ""
    message: str = ""


class SeedanceTaskResponse(BaseModel):
    """Full task object from the Seedance retrieve/list APIs."""

    id: str
    model: str = ""
    status: str = ""
    created_at: int | str | None = None
    updated_at: int | str | None = None
    error: SeedanceErrorDetail | None = None
    content: dict[str, Any] | None = None
    usage: SeedanceGenerationUsage | None = None
    # Generation settings (may be top-level or inside content).
    seed: int | None = None
    resolution: str | None = None
    ratio: str | None = None
    duration: int | str | None = None
    framespersecond: int | None = None
    service_tier: str | None = None
    execution_expires_after: int | None = None
    generate_audio: bool | None = None
    draft: bool | None = None
    priority: int | None = None

    @property
    def video_url(self) -> str | None:
        """Extract the video URL from the content object."""
        if self.content and isinstance(self.content, dict):
            url = self.content.get("video_url")
            if isinstance(url, str):
                return url
            if isinstance(url, dict):
                return url.get("url")
        return None

    @property
    def last_frame_url(self) -> str | None:
        """Extract the last frame URL from the content object."""
        if self.content and isinstance(self.content, dict):
            url = self.content.get("last_frame_url")
            if isinstance(url, str):
                return url
            if isinstance(url, dict):
                return url.get("url")
        return None


class SeedanceTaskListResponse(BaseModel):
    """Response from ``GET /contents/generations/tasks``."""

    data: list[SeedanceTaskResponse] = Field(default_factory=list)
    total: int = 0
    has_more: bool | None = None
