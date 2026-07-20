"""Shared media-source input models.

These types are used across tool inputs to describe image, audio, and video
references in a provider-agnostic way. Provider adapters translate them to
the specific provider DTOs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MediaSourceKind(StrEnum):
    """Whether a media source is a URL or inline Base64 data."""

    url = "url"
    base64 = "base64"


class MediaSource(BaseModel):
    """A media reference specified by URL or Base64 data.

    Exactly one of ``url`` or ``data`` must be set, matching ``kind``.
    """

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
        return self
