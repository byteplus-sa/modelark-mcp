"""ModelArk Seed Multimodal MCP Server — main server module.

This module creates the FastMCP instance, registers tools conditionally
based on configured credentials, registers the artifact resource template,
and provides the ``mcp`` entrypoint for ``fastmcp run``.

Implements the plan in ``plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import truststore

truststore.inject_into_ssl()

from fastmcp import Context, FastMCP  # noqa: E402
from fastmcp.resources import ResourceContent, ResourceResult  # noqa: E402

from modelark_mcp.artifacts.filesystem_store import FilesystemArtifactStore  # noqa: E402
from modelark_mcp.config.env import get_settings  # noqa: E402
from modelark_mcp.observability.logger import info as log_info  # noqa: E402
from modelark_mcp.security.auth_context import AuthContext  # noqa: E402

if TYPE_CHECKING:
    from modelark_mcp.artifacts.store import ArtifactStore

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    "ModelArk Seed Multimodal",
    instructions=(
        "BytePlus multimodal generation server. Provides tools for:\n"
        "- Seed Audio: full-scene audio generation through Seed Speech\n"
        "- Seedream: image generation and editing through ModelArk\n"
        "- Seedance: asynchronous video generation and task management through ModelArk\n"
        "Generated media is persisted as durable MCP resources."
    ),
)


# ---------------------------------------------------------------------------
# Artifact store singleton
# ---------------------------------------------------------------------------

_artifact_store: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    """Return the singleton artifact store."""
    global _artifact_store
    if _artifact_store is None:
        settings = get_settings()
        if settings.artifact_backend == "filesystem":
            _artifact_store = FilesystemArtifactStore()
        else:
            # Fall back to filesystem for MVP.
            _artifact_store = FilesystemArtifactStore()
    return _artifact_store


# ---------------------------------------------------------------------------
# Auth context derivation
# ---------------------------------------------------------------------------


def derive_auth_from_context(ctx: Context) -> AuthContext:
    """Derive the auth context from an MCP request context.

    In ``stdio`` mode, there is a single local principal. In remote HTTP
    mode, this would extract the principal ID and tenant from the OAuth
    token / request context.
    """
    return AuthContext(principal_id="local", tenant_id="local")


# ---------------------------------------------------------------------------
# Resource template: seed-media://artifacts/{artifact_id}
# ---------------------------------------------------------------------------


@mcp.resource("seed-media://artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, ctx: Context) -> ResourceResult:
    """Return persisted media by artifact ID with the correct MIME type.

    Supports audio (WAV, MP3, PCM, OGG), image (PNG, JPEG, WebP), and
    video (MP4) outputs. The correct MIME type is set from stored artifact
    metadata so the returned blob does not default to
    ``application/octet-stream``.
    """
    auth = derive_auth_from_context(ctx)
    store = get_artifact_store()
    artifact = await store.get(artifact_id, auth=auth)

    log_info(
        "artifact_served",
        artifact_id=artifact_id,
        media_type=artifact.media_type,
        mime_type=artifact.mime_type,
        bytes=len(artifact.data),
    )

    return ResourceResult(
        contents=[
            ResourceContent(
                content=artifact.data,
                mime_type=artifact.mime_type,
            )
        ],
        meta={
            "artifact_id": artifact_id,
            "media_type": artifact.media_type,
        },
    )


# ---------------------------------------------------------------------------
# Health resource
# ---------------------------------------------------------------------------


@mcp.resource("seed-health://status")
async def health_status() -> str:
    """Return the server health and configuration status."""
    settings = get_settings()
    return (
        f"ModelArk Seed MCP Server\n"
        f"Status: healthy\n"
        f"ModelArk configured: {settings.has_modelark}\n"
        f"Seed Audio configured: {settings.has_seed_audio}\n"
        f"Artifact backend: {settings.artifact_backend}\n"
        f"Transport: {settings.mcp_transport}\n"
    )


# ---------------------------------------------------------------------------
# Tool registration (conditional on credentials)
# ---------------------------------------------------------------------------


def register_tools() -> None:
    """Register tools conditionally based on configured credentials.

    If a credential is absent, the server does not register that product's
    tool set. This prevents exposing tools that would always fail.
    """
    settings = get_settings()

    if settings.has_seed_audio:
        from modelark_mcp.tools.seed_audio_generate import (
            TOOL_ANNOTATIONS as audio_annotations,
        )
        from modelark_mcp.tools.seed_audio_generate import (
            seed_audio_generate,
        )
        from modelark_mcp.tools.seed_audio_generate_variations import (
            TOOL_ANNOTATIONS as audio_var_annotations,
        )
        from modelark_mcp.tools.seed_audio_generate_variations import (
            seed_audio_generate_variations,
        )

        mcp.tool(
            name="seed_audio_generate",
            annotations={**audio_annotations},
        )(seed_audio_generate)
        log_info("tool_registered", tool="seed_audio_generate")

        mcp.tool(
            name="seed_audio_generate_variations",
            annotations={**audio_var_annotations},
        )(seed_audio_generate_variations)
        log_info("tool_registered", tool="seed_audio_generate_variations")

    if settings.has_modelark:
        from modelark_mcp.tools.seedance_cancel_or_delete_task import (
            TOOL_ANNOTATIONS as cancel_annotations,
        )
        from modelark_mcp.tools.seedance_cancel_or_delete_task import (
            seedance_cancel_or_delete_task,
        )
        from modelark_mcp.tools.seedance_create_task import (
            TOOL_ANNOTATIONS as create_annotations,
        )
        from modelark_mcp.tools.seedance_create_task import (
            seedance_create_task,
        )
        from modelark_mcp.tools.seedance_create_task_variations import (
            TOOL_ANNOTATIONS as seedance_var_annotations,
        )
        from modelark_mcp.tools.seedance_create_task_variations import (
            seedance_create_task_variations,
        )
        from modelark_mcp.tools.seedance_get_task import (
            TOOL_ANNOTATIONS as get_annotations,
        )
        from modelark_mcp.tools.seedance_get_task import (
            seedance_get_task,
        )
        from modelark_mcp.tools.seedance_list_tasks import (
            TOOL_ANNOTATIONS as list_annotations,
        )
        from modelark_mcp.tools.seedance_list_tasks import (
            seedance_list_tasks,
        )
        from modelark_mcp.tools.seedream_generate_image import (
            TOOL_ANNOTATIONS as seedream_annotations,
        )
        from modelark_mcp.tools.seedream_generate_image import (
            seedream_generate_image,
        )
        from modelark_mcp.tools.seedream_generate_image_variations import (
            TOOL_ANNOTATIONS as seedream_var_annotations,
        )
        from modelark_mcp.tools.seedream_generate_image_variations import (
            seedream_generate_image_variations,
        )

        mcp.tool(
            name="seedream_generate_image",
            annotations={**seedream_annotations},
        )(seedream_generate_image)
        log_info("tool_registered", tool="seedream_generate_image")

        mcp.tool(
            name="seedream_generate_image_variations",
            annotations={**seedream_var_annotations},
        )(seedream_generate_image_variations)
        log_info("tool_registered", tool="seedream_generate_image_variations")

        mcp.tool(
            name="seedance_create_task",
            annotations={**create_annotations},
        )(seedance_create_task)
        log_info("tool_registered", tool="seedance_create_task")

        mcp.tool(
            name="seedance_create_task_variations",
            annotations={**seedance_var_annotations},
        )(seedance_create_task_variations)
        log_info("tool_registered", tool="seedance_create_task_variations")

        mcp.tool(
            name="seedance_get_task",
            annotations={**get_annotations},
        )(seedance_get_task)
        log_info("tool_registered", tool="seedance_get_task")

        mcp.tool(
            name="seedance_list_tasks",
            annotations={**list_annotations},
        )(seedance_list_tasks)
        log_info("tool_registered", tool="seedance_list_tasks")

        mcp.tool(
            name="seedance_cancel_or_delete_task",
            annotations={**cancel_annotations},
        )(seedance_cancel_or_delete_task)
        log_info("tool_registered", tool="seedance_cancel_or_delete_task")
    else:
        log_info(
            "tools_skipped",
            reason="BYTEPLUS_MODELARK_API_KEY not configured",
        )


# Register tools at import time.
register_tools()
