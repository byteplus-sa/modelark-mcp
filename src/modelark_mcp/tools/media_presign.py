"""``media_presign`` tool — generate a fresh presigned URL for an existing object.

Accepts an object key returned by a prior ``media_upload`` call and generates
a new presigned HTTPS GET URL without re-uploading.  This avoids redundant
uploads when the same reference media is used across multiple generation calls
spread over time (e.g. several Seedance tasks throughout a day).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, field_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.object_storage import make_object_storage_gateway
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.runtime import billed_provider_slot
from modelark_mcp.tools._errors import provider_error_result

_OBJECT_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_/]*$")


class MediaPresignInput(BaseModel):
    """Input model for ``media_presign``."""

    object_key: str = Field(
        ...,
        description=(
            "Object key returned by a prior media_upload call (e.g. 'references/video/<uuid>')."
        ),
    )
    expires_in_seconds: int | None = Field(
        None,
        ge=60,
        le=604800,
        description=(
            "Presigned URL validity in seconds (60-604800). Defaults to the configured presign "
            "TTL. VOD tools fetch source URLs asynchronously, so use a long TTL (e.g. 3600) when "
            "renewing a URL for vod_separate_audio, vod_transcode_video, or vod_enhance_video."
        ),
    )

    @field_validator("object_key")
    @classmethod
    def _validate_object_key(cls, v: str) -> str:
        if not v or not _OBJECT_KEY_PATTERN.match(v):
            raise ValueError(
                "object_key must contain only alphanumeric characters, '-', '_', and '/', "
                "and must not start with '/' or '-'."
            )
        if "//" in v or v.endswith("/"):
            raise ValueError("object_key must not contain empty path segments.")
        return v


class MediaPresignOutput(BaseModel):
    """Output model for ``media_presign``."""

    url: str = Field(..., description="Presigned HTTPS GET URL for the object.")
    expires_at: str = Field(..., description="ISO-8601 timestamp when the URL expires.")
    object_key: str = Field(..., description="Object key the URL grants access to.")


async def media_presign(input: MediaPresignInput, ctx: Context) -> MediaPresignOutput | ToolResult:
    """Generate a fresh presigned HTTPS GET URL for an existing object in storage.

    Use this when a previously uploaded reference's presigned URL has expired
    or is about to expire.  The object must already exist in the bucket (uploaded
    via ``media_upload``).  No data is transferred — only a new URL is minted.
    """
    await ctx.info("Generating presigned URL")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_object_storage:
        raise ValueError(
            "Object storage is not configured. Set TOS_* or S3_* credentials and "
            "OBJECT_STORAGE_BACKEND (tos|s3)."
        )

    await ctx.report_progress(progress=30, total=100)

    gateway = make_object_storage_gateway(settings)
    try:
        async with billed_provider_slot(
            ctx,
            provider=settings.object_storage_backend,
            product="presign",
            estimated_cost_usd=0.0,
        ):
            if input.expires_in_seconds is not None:
                url = await call_with_retry(
                    lambda: gateway.presign_get(
                        key=input.object_key, expires=input.expires_in_seconds
                    )
                )
            else:
                url = await call_with_retry(lambda: gateway.presign_get(key=input.object_key))
    except ProviderError as exc:
        await ctx.error(f"Presign failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await gateway.close()

    ttl = input.expires_in_seconds or settings.presign_ttl_seconds
    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat()

    await ctx.report_progress(progress=100, total=100)
    log_info("media_presign_complete", object_key=input.object_key)

    return MediaPresignOutput(
        url=url,
        expires_at=expires_at,
        object_key=input.object_key,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
