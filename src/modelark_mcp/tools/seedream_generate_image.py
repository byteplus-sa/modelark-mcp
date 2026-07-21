"""``seedream_generate_image`` tool — image generation and editing through ModelArk.

The handler derives ``sequential_image_generation`` from ``max_images``,
forces ``stream: false`` for MVP, and validates model-specific features.
For example, Pro rejects batch/streaming fields, and 4.x rejects
``output_format`` until the API-reference/tutorial conflict is resolved.
"""

from __future__ import annotations

from datetime import UTC
from typing import Literal

from fastmcp import Context
from pydantic import BaseModel, Field

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import get_capability_registry
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import MediaSource
from modelark_mcp.domain.models import SeedreamItemError, SeedreamUsage
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedream import SeedreamService

# ---------------------------------------------------------------------------
# Input / Output models
# ---------------------------------------------------------------------------


class SeedreamGenerateInput(BaseModel):
    """Input model for ``seedream_generate_image``."""

    prompt: str
    images: list[MediaSource] | None = None
    model: str | None = None
    size: str | None = None
    max_images: int | None = Field(None, ge=1, le=15)
    output_format: Literal["png", "jpeg"] | None = None
    response_format: Literal["url", "b64_json"] | None = None
    watermark: bool | None = None
    prompt_optimization: Literal["standard", "fast"] | None = None
    persist: bool = True


class SeedreamGenerateOutput(BaseModel):
    """Output model for ``seedream_generate_image``."""

    provider: Literal["byteplus-modelark"] = "byteplus-modelark"
    model: str
    created_at: str
    artifacts: list[ArtifactRef]
    item_errors: list[SeedreamItemError]
    usage: SeedreamUsage


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------


async def seedream_generate_image(
    input: SeedreamGenerateInput, ctx: Context
) -> SeedreamGenerateOutput:
    """Generate or edit an image through ModelArk Seedream.

    Supports text-to-image and reference-based editing. The ``max_images``
    parameter enables batch generation for models that support it (Lite,
    4.x). Pro models are limited to single-image generation.
    """
    await ctx.info("Starting Seedream image generation")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError(
            "BYTEPLUS_MODELARK_API_KEY is not configured. Set it in .env to enable Seedream tools."
        )

    registry = get_capability_registry()
    caps = registry.get_image_capabilities(input.model)

    # Validate model-specific features.
    if input.max_images and input.max_images > 1 and not caps.supports_batch:
        raise ValueError(
            f"Model '{caps.model_id}' does not support batch generation. "
            f"Set max_images to 1 or omit it."
        )

    if len(input.images or []) > caps.max_references:
        raise ValueError(
            f"Model '{caps.model_id}' supports at most {caps.max_references} "
            f"reference images, got {len(input.images or [])}."
        )

    registry.validate_output_format(input.model, input.output_format)
    registry.validate_image_size(input.model, input.size)

    await ctx.report_progress(progress=30, total=100)

    # Build the provider request.
    images_data = None
    if input.images:
        images_data = [src.model_dump() for src in input.images]

    request = SeedreamService.build_request(
        model=caps.model_id,
        prompt=input.prompt,
        images=images_data,
        size=input.size,
        max_images=input.max_images,
        output_format=input.output_format,
        response_format=input.response_format,
        watermark=input.watermark,
        prompt_optimization=input.prompt_optimization,
    )

    await ctx.report_progress(progress=50, total=100)

    service = SeedreamService()
    try:
        response, request_id = await service.generate(request)
    except ProviderError as exc:
        await ctx.error(f"Seedream generation failed: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=80, total=100)

    # Persist artifacts.
    artifacts: list[ArtifactRef] = []
    if input.persist:
        from modelark_mcp.server import get_artifact_store

        store = get_artifact_store()
        from datetime import datetime, timedelta

        source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()

        for item in response.data:
            if item.b64_json:
                ref = await store.put_base64(
                    data=item.b64_json,
                    media_type="image",
                    mime_type=(
                        f"image/{input.output_format}" if input.output_format else "image/png"
                    ),
                    source_expires_at=source_expiry,
                )
                artifacts.append(ref)
            elif item.url:
                ref = await store.copy_from_trusted_url(
                    url=item.url,
                    media_type="image",
                    mime_type=(
                        f"image/{input.output_format}" if input.output_format else "image/png"
                    ),
                    source_expires_at=source_expiry,
                )
                artifacts.append(ref)
    else:
        # Return unpersisted references to provider URLs (will expire).
        from datetime import datetime, timedelta

        source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        for item in response.data:
            if item.url:
                artifacts.append(
                    ArtifactRef(
                        id="provider-url",
                        uri=item.url,
                        media_type="image",
                        mime_type=f"image/{input.output_format or 'png'}",
                        created_at=datetime.now(UTC).isoformat(),
                        source_expires_at=source_expiry,
                    )
                )

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedream_complete",
        model=caps.model_id,
        artifacts_count=len(artifacts),
        request_id=request_id,
    )

    return SeedreamGenerateOutput(
        model=caps.model_id,
        created_at=SeedreamService.get_created_at(response),
        artifacts=artifacts,
        item_errors=SeedreamService.extract_item_errors(response),
        usage=SeedreamService.extract_usage(response),
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}
