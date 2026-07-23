"""Shared media-source input models.

These types are used across tool inputs to describe image, audio, and video
references in a provider-agnostic way. Provider adapters translate them to
the specific provider DTOs.

All user-supplied URLs are validated through the SSRF-safe ``validate_url``
policy, and Base64 data is size-checked via ``check_base64_size`` before
reaching the provider.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from modelark_mcp.domain.artifacts import MediaType
from modelark_mcp.security.media_policy import (
    check_base64_size,
    get_media_limits,
    validate_audio_mime,
    validate_image_mime,
    validate_video_mime,
)
from modelark_mcp.security.url_policy import validate_url


class MediaSourceKind(StrEnum):
    """Whether a media source is a URL or inline Base64 data."""

    url = "url"
    base64 = "base64"


class MediaSource(BaseModel):
    """A media reference specified by URL or Base64 data.

    Exactly one of ``url`` or ``data`` must be set, matching ``kind``.
    """

    MEDIA_CATEGORY: ClassVar[MediaType] = MediaType.IMAGE

    kind: MediaSourceKind = Field(
        ..., description="Whether the media is referenced by URL or Base64."
    )
    url: str | None = Field(
        default=None,
        description="HTTPS URL of the media. Required when kind is 'url'.",
    )
    data: str | None = Field(
        default=None,
        description="Base64-encoded media data. Required when kind is 'base64'.",
    )
    mime_type: str | None = Field(
        default=None,
        description="MIME type of the media (e.g. image/png, audio/wav).",
    )

    @model_validator(mode="after")
    def validate_source(self) -> MediaSource:
        if self.kind == MediaSourceKind.url and not self.url:
            raise ValueError("url is required when kind is 'url'")
        if self.kind == MediaSourceKind.base64 and not self.data:
            raise ValueError("data is required when kind is 'base64'")
        if self.kind == MediaSourceKind.url and self.data:
            raise ValueError("data must not be set when kind is 'url'")
        if self.kind == MediaSourceKind.base64 and self.url:
            raise ValueError("url must not be set when kind is 'base64'")

        if self.kind == MediaSourceKind.url and self.url:
            validate_url(self.url)

        if self.kind == MediaSourceKind.base64 and self.data:
            limits = get_media_limits()
            media_category = type(self).MEDIA_CATEGORY
            max_bytes = {
                "image": limits.image_max_bytes,
                "audio": limits.audio_max_bytes,
                "video": limits.video_max_bytes,
            }[media_category]
            check_base64_size(self.data, max_bytes, label=media_category)

        if self.mime_type:
            media_category = type(self).MEDIA_CATEGORY
            if media_category == "image":
                validate_image_mime(self.mime_type)
            elif media_category == "audio":
                validate_audio_mime(self.mime_type)
            elif media_category == "video":
                validate_video_mime(self.mime_type)

        return self


class AudioReference(BaseModel):
    """An audio reference for Seed Audio, using one of three modes."""

    kind: Literal["speaker", "url", "base64"] = Field(
        ...,
        description="Reference mode: speaker ID, URL, or Base64 data.",
    )
    speaker_id: str | None = Field(
        default=None,
        description="Predefined speaker ID. Required when kind is 'speaker'.",
    )
    url: str | None = Field(
        default=None, description="HTTPS URL of the reference audio. Required when kind is 'url'."
    )
    data: str | None = Field(
        default=None,
        description="Base64-encoded reference audio. Required when kind is 'base64'.",
    )
    mime_type: str | None = Field(
        default=None,
        description="MIME type of the reference audio.",
    )

    @model_validator(mode="after")
    def validate_reference(self) -> AudioReference:
        if self.kind == "speaker" and not self.speaker_id:
            raise ValueError("speaker_id is required when kind is 'speaker'")
        if self.kind == "url" and not self.url:
            raise ValueError("url is required when kind is 'url'")
        if self.kind == "base64" and not self.data:
            raise ValueError("data is required when kind is 'base64'")
        if self.kind == "speaker" and (self.url or self.data):
            raise ValueError("url/data must not be set when kind is 'speaker'")
        if self.kind == "url" and (self.speaker_id or self.data):
            raise ValueError("speaker_id/data must not be set when kind is 'url'")
        if self.kind == "base64" and (self.speaker_id or self.url):
            raise ValueError("speaker_id/url must not be set when kind is 'base64'")

        if self.kind == "url" and self.url:
            validate_url(self.url)

        if self.kind == "base64" and self.data:
            limits = get_media_limits()
            check_base64_size(self.data, limits.audio_max_bytes, label="audio")

        if self.mime_type:
            validate_audio_mime(self.mime_type)

        return self
