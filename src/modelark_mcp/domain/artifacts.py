"""Domain artifact models.

``ArtifactRef`` is the stable cross-tool contract for persisted media. Every
successful tool result returns one or more ``ArtifactRef`` instances that
point to durable ``seed-media://artifacts/{id}`` resources, so MCP clients
can retrieve media long after the provider URL expires (2h for audio,
24h for image/video).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MediaType(StrEnum):
    """Logical generated-media categories."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class ArtifactRef(BaseModel):
    """Stable reference to a persisted media artifact."""

    id: str = Field(..., description="Unique artifact identifier.")
    uri: str = Field(..., description="MCP resource URI (seed-media://artifacts/{id}).")
    media_type: MediaType = Field(..., description="Logical media type: image, audio, or video.")
    mime_type: str = Field(..., description="MIME type of the stored content (e.g. image/png).")
    bytes: int | None = Field(default=None, description="Size of the stored content in bytes.")
    sha256: str | None = Field(
        default=None, description="SHA-256 hex digest of the stored content."
    )
    created_at: str = Field(..., description="ISO-8601 timestamp of artifact creation.")
    expires_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when the local artifact expires.",
    )
    source_expires_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when the provider URL expires.",
    )
