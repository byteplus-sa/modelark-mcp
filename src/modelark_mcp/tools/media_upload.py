"""``media_upload`` tool — upload media to BytePlus TOS, return a presigned URL.

Accepts Base64-encoded bytes or a local file path (stdio transport only),
uploads to a configured TOS bucket, and returns a presigned HTTPS GET URL
that can be passed to other tools (e.g. ``seedance_create_task`` video
references).  This is the integrated path for media that cannot be inlined
as Base64 — most notably Seedance video references, which are URL-only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.providers.tos.client import TosGateway
from modelark_mcp.runtime import billed_provider_slot
from modelark_mcp.security.media_policy import (
    MediaLimits,
    check_base64_size,
    decode_base64_safely,
    get_media_limits,
    validate_audio_mime,
    validate_image_mime,
    validate_video_mime,
)
from modelark_mcp.tools._errors import provider_error_result


class MediaUploadInput(BaseModel):
    """Input model for ``media_upload``."""

    media_type: Literal["image", "audio", "video"] = Field(
        ..., description="Media category for MIME and size validation."
    )
    mime_type: str = Field(
        ...,
        description="MIME type of the media (e.g. 'video/mp4', 'image/png', 'audio/wav').",
    )
    data: str | None = Field(
        None,
        description="Base64-encoded media bytes. Mutually exclusive with file_path.",
    )
    file_path: str | None = Field(
        None,
        description=(
            "Absolute path to a local file. stdio transport only. Mutually exclusive with data."
        ),
    )
    key_prefix: str | None = Field(
        None,
        description=(
            "Optional TOS object key prefix (default 'references'). "
            "Alphanumeric, '-', '_', '/' only."
        ),
    )

    @model_validator(mode="after")
    def _validate_input(self) -> MediaUploadInput:
        if bool(self.data) == bool(self.file_path):
            raise ValueError("Provide exactly one of 'data' (Base64) or 'file_path'.")
        self._validate_mime_type()
        if self.data is not None:
            limits = get_media_limits()
            max_bytes = _max_bytes(limits, self.media_type)
            check_base64_size(self.data, max_bytes, label=self.media_type)
        if self.key_prefix:
            self._validate_key_prefix()
        return self

    def _validate_mime_type(self) -> None:
        match self.media_type:
            case "image":
                validate_image_mime(self.mime_type)
            case "audio":
                validate_audio_mime(self.mime_type)
            case "video":
                validate_video_mime(self.mime_type)

    def _validate_key_prefix(self) -> None:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/ ")
        if self.key_prefix and not set(self.key_prefix) <= allowed:
            raise ValueError(
                "key_prefix may only contain alphanumeric characters, '-', '_', and '/'."
            )


class MediaUploadOutput(BaseModel):
    """Output model for ``media_upload``."""

    url: str = Field(..., description="Presigned HTTPS GET URL for the uploaded object.")
    expires_at: str = Field(..., description="ISO-8601 timestamp when the URL expires.")
    object_key: str = Field(..., description="TOS object key of the uploaded media.")
    bytes: int = Field(..., description="Uploaded byte count.")


def _max_bytes(limits: MediaLimits, media_type: str) -> int:
    return {
        "image": limits.image_max_bytes,
        "audio": limits.audio_max_bytes,
        "video": limits.video_max_bytes,
    }[media_type]


async def media_upload(input: MediaUploadInput, ctx: Context) -> MediaUploadOutput | ToolResult:
    """Upload media to BytePlus TOS and return a presigned HTTPS GET URL.

    The returned URL can be passed directly to tools that accept media URLs,
    such as ``seedance_create_task`` (video references).  Video references are
    URL-only — this tool is the integrated upload path for them.
    """
    await ctx.info("Starting TOS media upload")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_tos:
        raise ValueError(
            "TOS credentials are not configured. Set TOS_ACCESS_KEY and TOS_SECRET_KEY."
        )

    limits = get_media_limits()
    max_bytes = _max_bytes(limits, input.media_type)

    path: Path | None = None
    raw: bytes | None = None

    if input.file_path is not None:
        if settings.mcp_transport != "stdio":
            raise ValueError(
                "file_path input is only supported in stdio transport mode for security."
            )
        path = Path(input.file_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"File not found: {input.file_path}")
        file_size = path.stat().st_size
        if file_size > max_bytes:
            raise ValueError(
                f"{input.media_type} file size ({file_size} bytes) exceeds "
                f"limit ({max_bytes} bytes)."
            )
        raw_size = file_size
    else:
        if input.data is None:
            raise ValueError("data is required when file_path is not provided.")
        raw = decode_base64_safely(input.data, max_bytes, label=input.media_type)
        raw_size = len(raw)

    await ctx.report_progress(progress=30, total=100)

    prefix = input.key_prefix or "references"
    key = f"{prefix}/{input.media_type}/{uuid4()}"

    gateway = TosGateway()
    try:
        async with billed_provider_slot(
            ctx,
            provider="tos",
            product="upload",
            estimated_cost_usd=0.0,
        ):
            if path is not None:
                file_path_str = str(path)
                await call_with_retry(
                    lambda: gateway.upload_file(
                        key=key, file_path=file_path_str, mime_type=input.mime_type
                    )
                )
            else:
                if raw is None:
                    raise ValueError("data is required for Base64 upload.")
                data_bytes = raw
                await call_with_retry(
                    lambda: gateway.upload_bytes(
                        key=key, data=data_bytes, mime_type=input.mime_type
                    )
                )
            url = await gateway.presign_get(key=key)
    except ProviderError as exc:
        await ctx.error(f"TOS upload failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await gateway.close()

    expires_at = (
        datetime.now(UTC) + timedelta(seconds=settings.tos_presign_ttl_seconds)
    ).isoformat()

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "media_upload_complete",
        object_key=key,
        media_type=input.media_type,
        bytes=raw_size,
    )

    return MediaUploadOutput(
        url=url,
        expires_at=expires_at,
        object_key=key,
        bytes=raw_size,
    )


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
