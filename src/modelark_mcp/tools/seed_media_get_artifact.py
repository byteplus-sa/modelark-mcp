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
    artifact_id: str
    media_type: MediaType
    mime_type: str
    sha256: str
    bytes: int
    expires_at: str | None = None
    data: str = Field(..., description="Base64-encoded media data.")


async def seed_media_get_artifact(
    input: SeedMediaGetArtifactInput, ctx: Context
) -> SeedMediaGetArtifactOutput | ToolResult:
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
