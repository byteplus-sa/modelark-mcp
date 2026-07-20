"""Seed Speech provider schemas (Seed Audio).

Provider DTOs for the Seed Audio 1.0 API — ``POST /api/v3/tts/create``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SeedAudioReferenceItem(BaseModel):
    """A single reference in the Seed Audio provider request."""

    speaker: str | None = None
    audio_url: str | None = None
    audio_data: str | None = None


class SeedAudioImageReferenceItem(BaseModel):
    """Image reference for the Seed Audio provider request."""

    image_url: str | None = None
    image_data: str | None = None


class SeedAudioProviderRequest(BaseModel):
    """Raw request body for ``POST /api/v3/tts/create``."""

    model: str = "seed-audio-1.0"
    text_prompt: str
    references: list[dict[str, Any]] | None = None
    output: dict[str, Any] | None = None
    watermark: dict[str, Any] | None = None


class SeedAudioSubtitle(BaseModel):
    """Subtitle data in the Seed Audio provider response."""

    utterances: list[dict[str, Any]] = Field(default_factory=list)
    words: list[dict[str, Any]] = Field(default_factory=list)


class SeedAudioProviderResponse(BaseModel):
    """Raw response from ``POST /api/v3/tts/create``."""

    code: int = 0
    message: str = ""
    audio: str | None = None  # Base64
    duration: float | None = None
    original_duration: float | None = None
    url: str | None = None
    subtitle: SeedAudioSubtitle | None = None
