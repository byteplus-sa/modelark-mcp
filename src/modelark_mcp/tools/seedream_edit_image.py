"""``seedream_edit_image`` tool — interactive image editing through ModelArk.

Exposes Seedream 5.0 Pro interactive editing with structured coordinate
inputs (point and bounding-box). The handler constructs ``<point>`` and
``<bbox>`` markup from validated coordinates, then delegates to the
existing ``SeedreamService`` for generation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import get_capability_registry
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.media import MediaSource
from modelark_mcp.domain.models import SeedreamItemError, SeedreamUsage
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedream import SeedreamService
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.runtime import billed_provider_slot, get_principal, get_runtime
from modelark_mcp.tools._cost import log_cost_estimate
from modelark_mcp.tools._errors import provider_error_result


class EditCoordinate(BaseModel):
    """Normalized point coordinate (0-999) for interactive editing."""

    x: int = Field(..., ge=0, le=999, description="Horizontal position, 0=left, 999=right.")
    y: int = Field(..., ge=0, le=999, description="Vertical position, 0=top, 999=bottom.")


class EditBbox(BaseModel):
    """Normalized bounding-box (0-999) for region-based editing."""

    x1: int = Field(..., ge=0, le=999, description="Left edge.")
    y1: int = Field(..., ge=0, le=999, description="Top edge.")
    x2: int = Field(..., ge=0, le=999, description="Right edge.")
    y2: int = Field(..., ge=0, le=999, description="Bottom edge.")

    @model_validator(mode="after")
    def validate_ordering(self) -> EditBbox:
        if self.x1 > self.x2:
            raise ValueError(f"x1 ({self.x1}) must not exceed x2 ({self.x2})")
        if self.y1 > self.y2:
            raise ValueError(f"y1 ({self.y1}) must not exceed y2 ({self.y2})")
        return self


class SeedreamEditInput(BaseModel):
    """Input model for ``seedream_edit_image``."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Natural-language edit instruction (e.g. 'Replace the object with a crown'). Coordinate markup is added automatically.",
    )
    images: list[MediaSource] = Field(
        ...,
        min_length=1,
        description="Reference images to edit. At least one is required.",
    )
    point: EditCoordinate | None = Field(
        None, description="Point coordinate for object-level editing near a position."
    )
    bbox: EditBbox | None = Field(
        None, description="Bounding-box coordinate for region-based editing."
    )
    model: str | None = Field(
        None,
        description=(
            "Model ID. Default: 'dola-seedream-5-0-pro-260628' (Pro, 10 refs, PNG/JPEG). "
            "Lite and 4x model IDs are configured via SEEDREAM_MODEL_BINDINGS."
        ),
    )
    size: str | None = Field(None, description="Output image size (e.g. '1024x1024', '2048x1152').")
    seed: int | None = Field(
        None, ge=-1, le=2147483647, description="Random seed. -1 = random, 0+ = fixed."
    )
    output_format: Literal["png", "jpeg"] | None = Field(
        None, description="Output image format. Not supported by 4.x models."
    )
    response_format: Literal["url", "b64_json"] | None = Field(
        None, description="Response format: URL or Base64 JSON."
    )
    watermark: bool | None = Field(
        None, description="Whether to apply an AIGC watermark to generated images."
    )
    prompt_optimization: Literal["standard", "fast"] | None = Field(
        None,
        description="Prompt optimization mode: standard (higher quality) or fast (lower latency).",
    )
    persist: bool = Field(
        True, description="Whether to persist generated images as durable MCP resources."
    )

    @model_validator(mode="after")
    def validate_coordinate_provided(self) -> SeedreamEditInput:
        if self.point is None and self.bbox is None:
            raise ValueError("At least one of 'point' or 'bbox' must be provided for editing.")
        return self


class SeedreamEditOutput(BaseModel):
    """Output model for ``seedream_edit_image``."""

    provider: Literal["byteplus-modelark"] = "byteplus-modelark"
    model: str
    created_at: str
    artifacts: list[ArtifactRef]
    item_errors: list[SeedreamItemError]
    usage: SeedreamUsage


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


def _build_edit_prompt(
    instruction: str, images: list[MediaSource], point: EditCoordinate | None, bbox: EditBbox | None
) -> str:
    """Build the full prompt with coordinate markup prepended."""
    parts: list[str] = []
    if bbox is not None:
        parts.append(f"Image 1<bbox>{bbox.x1} {bbox.y1} {bbox.x2} {bbox.y2}</bbox>")
    if point is not None:
        parts.append(f"Image 1<point>{point.x} {point.y}</point>")
    parts.append(instruction)
    return " ".join(parts)


async def seedream_edit_image(
    input: SeedreamEditInput, ctx: Context
) -> SeedreamEditOutput | ToolResult:
    """Edit an image interactively through ModelArk Seedream.

    Supports point-based and bounding-box editing by constructing coordinate
    markup (``<point>`` / ``<bbox>``) from structured inputs. At least one
    reference image and one coordinate (point or bbox) are required.
    """
    await ctx.info("Starting Seedream image edit")
    await ctx.report_progress(progress=10, total=100)

    settings = get_settings()
    if not settings.has_modelark:
        raise ValueError(
            "BYTEPLUS_MODELARK_API_KEY is not configured. Set it in .env to enable Seedream tools."
        )

    registry = get_capability_registry()
    caps = registry.get_image_capabilities(input.model)

    if len(input.images) > caps.max_references:
        raise ValueError(
            f"Model '{caps.model_id}' supports at most {caps.max_references} "
            f"reference images, got {len(input.images)}."
        )

    registry.validate_output_format(input.model, input.output_format)
    registry.validate_image_size(input.model, input.size)

    await ctx.report_progress(progress=30, total=100)

    full_prompt = _build_edit_prompt(input.prompt, input.images, input.point, input.bbox)

    images_data = [src.model_dump() for src in input.images]

    request = SeedreamService.build_request(
        model=caps.model_id,
        prompt=full_prompt,
        images=images_data,
        size=input.size,
        seed=input.seed,
        output_format=input.output_format,
        response_format=input.response_format,
        watermark=input.watermark,
        prompt_optimization=input.prompt_optimization,
    )

    await ctx.report_progress(progress=50, total=100)

    estimated_cost = log_cost_estimate(product="image", variations=1)

    service = SeedreamService()
    try:
        async with billed_provider_slot(
            ctx,
            provider="modelark",
            product="image",
            estimated_cost_usd=estimated_cost,
        ):
            response, request_id = await call_with_retry(lambda: service.generate(request))
    except ProviderError as exc:
        await ctx.error(f"Seedream edit failed: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=80, total=100)

    artifacts: list[ArtifactRef] = []
    if input.persist:
        store = get_runtime(ctx).artifact_store
        owner = get_principal(ctx)

        source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()

        for item in response.data:
            mime_type = f"image/{item.output_format or input.output_format or 'jpeg'}"
            if item.b64_json:
                ref = await store.put_base64(
                    data=item.b64_json,
                    media_type=MediaType.IMAGE,
                    mime_type=mime_type,
                    source_expires_at=source_expiry,
                    auth=owner,
                )
                artifacts.append(ref)
            elif item.url:
                ref = await store.copy_from_trusted_url(
                    url=item.url,
                    media_type=MediaType.IMAGE,
                    mime_type=mime_type,
                    source_expires_at=source_expiry,
                    auth=owner,
                )
                artifacts.append(ref)
    else:
        source_expiry = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
        for item in response.data:
            if item.url:
                artifacts.append(
                    ArtifactRef(
                        id="provider-url",
                        uri=item.url,
                        media_type=MediaType.IMAGE,
                        mime_type=f"image/{item.output_format or input.output_format or 'jpeg'}",
                        created_at=datetime.now(UTC).isoformat(),
                        source_expires_at=source_expiry,
                    )
                )

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedream_edit_complete",
        model=caps.model_id,
        artifacts_count=len(artifacts),
        request_id=request_id,
    )

    return SeedreamEditOutput(
        model=caps.model_id,
        created_at=SeedreamService.get_created_at(response),
        artifacts=artifacts,
        item_errors=SeedreamService.extract_item_errors(response),
        usage=SeedreamService.extract_usage(response),
    )
