"""seed_media_get_artifact tool - retrieve persisted media by artifact ID."""

from __future__ import annotations

import base64
import hashlib

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from modelark_mcp.domain.artifacts import MediaType
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.runtime import get_principal, get_runtime


class SeedMediaGetArtifactInput(BaseModel):
    artifact_id: str = Field(
        ...,
        min_length=1,
        description="The artifact ID returned by a previous generation call.",
    )


class SeedMediaGetArtifactOutput(BaseModel):
    """Output model for ``seed_media_get_artifact``."""

    artifact_id: str = Field(..., description="Unique artifact identifier.")
    media_type: MediaType = Field(..., description="Logical media type: image, audio, or video.")
    mime_type: str = Field(..., description="MIME type of the stored content (e.g. image/png).")
    sha256: str = Field(..., description="SHA-256 hex digest of the stored content.")
    bytes: int = Field(..., description="Size of the stored content in bytes.")
    expires_at: str | None = Field(
        None, description="ISO-8601 timestamp when the local artifact expires, if applicable."
    )
    data: str = Field(..., description="Base64-encoded media data.")


async def seed_media_get_artifact(
    input: SeedMediaGetArtifactInput, ctx: Context
) -> SeedMediaGetArtifactOutput | ToolResult:
    """Retrieve persisted media by its artifact ID.

    Returns the raw media bytes (Base64-encoded) along with metadata such as
    MIME type, SHA-256 hash, and byte count. Use this to fetch media that was
    persisted by a previous generation call after the provider URL has expired
    (2h for audio, 24h for image/video).
    """
    await ctx.info(f"Fetching artifact {input.artifact_id}")

    runtime = get_runtime(ctx)
    auth = get_principal(ctx)

    stored = await runtime.artifact_store.get(input.artifact_id, auth=auth)

    sha256 = hashlib.sha256(stored.data).hexdigest()
    b64_data = base64.b64encode(stored.data).decode("ascii")

    log_info(
        "artifact_fetched",
        artifact_id=input.artifact_id,
        media_type=stored.media_type,
        mime_type=stored.mime_type,
        bytes=len(stored.data),
    )

    return SeedMediaGetArtifactOutput(
        artifact_id=input.artifact_id,
        media_type=stored.media_type,
        mime_type=stored.mime_type,
        sha256=sha256,
        bytes=len(stored.data),
        data=b64_data,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
