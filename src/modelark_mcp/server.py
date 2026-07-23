"""FastMCP server factory and module-level deployment entrypoint.

Implements ``plans/PLAN_CODEBASE_GAP_REMEDIATION.md``. Runtime resources are
created once by the FastMCP lifespan; importing this module only assembles the
declarative server surface.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import truststore

truststore.inject_into_ssl()

from fastmcp import Context, FastMCP  # noqa: E402
from fastmcp.resources import ResourceContent, ResourceResult  # noqa: E402
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # noqa: E402
from starlette.responses import JSONResponse, Response  # noqa: E402

if TYPE_CHECKING:
    from fastmcp.server.auth import AuthProvider
    from starlette.requests import Request

from modelark_mcp.config.env import Settings, get_settings  # noqa: E402
from modelark_mcp.observability.logger import info as log_info  # noqa: E402
from modelark_mcp.observability.logger import set_level  # noqa: E402
from modelark_mcp.observability.metrics import MetricsMiddleware  # noqa: E402
from modelark_mcp.runtime import (  # noqa: E402
    RuntimeFactory,
    RuntimeState,
    build_lifespan,
    create_runtime_services,
    get_principal,
    get_runtime,
)
from modelark_mcp.security.http_auth import (  # noqa: E402
    build_auth_provider,
    component_auth,
)


def register_tools(server: FastMCP, settings: Settings) -> None:
    """Register configured tools on one server instance."""
    if settings.has_seed_audio:
        from modelark_mcp.tools.seed_audio_generate import (
            TOOL_ANNOTATIONS as audio_annotations,
        )
        from modelark_mcp.tools.seed_audio_generate import (
            SeedAudioGenerateOutput,
            seed_audio_generate,
        )
        from modelark_mcp.tools.seed_audio_generate_variations import (
            TOOL_ANNOTATIONS as audio_var_annotations,
        )
        from modelark_mcp.tools.seed_audio_generate_variations import (
            SeedAudioVariationsOutput,
            seed_audio_generate_variations,
        )

        server.tool(
            name="seed_audio_generate",
            annotations={**audio_annotations},
            output_schema=SeedAudioGenerateOutput.model_json_schema(),
            auth=component_auth(settings, "seed:audio:generate"),
        )(seed_audio_generate)
        server.tool(
            name="seed_audio_generate_variations",
            annotations={**audio_var_annotations},
            output_schema=SeedAudioVariationsOutput.model_json_schema(),
            auth=component_auth(settings, "seed:audio:generate"),
        )(seed_audio_generate_variations)

    if settings.has_tos:
        from modelark_mcp.tools.media_upload import (
            TOOL_ANNOTATIONS as upload_annotations,
        )
        from modelark_mcp.tools.media_upload import (
            MediaUploadOutput,
            media_upload,
        )

        server.tool(
            name="media_upload",
            annotations={**upload_annotations},
            output_schema=MediaUploadOutput.model_json_schema(),
            auth=component_auth(settings, "media:upload"),
        )(media_upload)

    if not settings.has_modelark:
        log_info("tools_skipped", reason="BYTEPLUS_MODELARK_API_KEY not configured")
        return

    from modelark_mcp.tools.seedance_cancel_or_delete_task import (
        TOOL_ANNOTATIONS as cancel_annotations,
    )
    from modelark_mcp.tools.seedance_cancel_or_delete_task import (
        SeedanceCancelOrDeleteOutput,
        seedance_cancel_or_delete_task,
    )
    from modelark_mcp.tools.seedance_create_task import (
        TOOL_ANNOTATIONS as create_annotations,
    )
    from modelark_mcp.tools.seedance_create_task import (
        SeedanceCreateTaskOutput,
        seedance_create_task,
    )
    from modelark_mcp.tools.seedance_create_task_variations import (
        TOOL_ANNOTATIONS as seedance_var_annotations,
    )
    from modelark_mcp.tools.seedance_create_task_variations import (
        SeedanceVariationsOutput,
        seedance_create_task_variations,
    )
    from modelark_mcp.tools.seedance_get_task import TOOL_ANNOTATIONS as get_annotations
    from modelark_mcp.tools.seedance_get_task import SeedanceTaskOutput, seedance_get_task
    from modelark_mcp.tools.seedance_list_tasks import TOOL_ANNOTATIONS as list_annotations
    from modelark_mcp.tools.seedance_list_tasks import SeedanceTaskPage, seedance_list_tasks
    from modelark_mcp.tools.seedream_generate_image import (
        TOOL_ANNOTATIONS as seedream_annotations,
    )
    from modelark_mcp.tools.seedream_generate_image import (
        SeedreamGenerateOutput,
        seedream_generate_image,
    )
    from modelark_mcp.tools.seedream_generate_image_variations import (
        TOOL_ANNOTATIONS as seedream_var_annotations,
    )
    from modelark_mcp.tools.seedream_generate_image_variations import (
        SeedreamVariationsOutput,
        seedream_generate_image_variations,
    )

    registrations = (
        (
            "seedream_generate_image",
            seedream_annotations,
            SeedreamGenerateOutput,
            "seedream:generate",
            seedream_generate_image,
        ),
        (
            "seedream_generate_image_variations",
            seedream_var_annotations,
            SeedreamVariationsOutput,
            "seedream:generate",
            seedream_generate_image_variations,
        ),
        (
            "seedance_create_task",
            create_annotations,
            SeedanceCreateTaskOutput,
            "seedance:create",
            seedance_create_task,
        ),
        (
            "seedance_create_task_variations",
            seedance_var_annotations,
            SeedanceVariationsOutput,
            "seedance:create",
            seedance_create_task_variations,
        ),
        (
            "seedance_get_task",
            get_annotations,
            SeedanceTaskOutput,
            "seedance:read",
            seedance_get_task,
        ),
        (
            "seedance_list_tasks",
            list_annotations,
            SeedanceTaskPage,
            "seedance:read",
            seedance_list_tasks,
        ),
        (
            "seedance_cancel_or_delete_task",
            cancel_annotations,
            SeedanceCancelOrDeleteOutput,
            "seedance:delete",
            seedance_cancel_or_delete_task,
        ),
    )
    for name, tool_annotations, output_model, scope, handler in registrations:
        server.tool(
            name=name,
            annotations={**tool_annotations},
            output_schema=output_model.model_json_schema(),
            auth=component_auth(settings, scope),
        )(handler)


def create_server(
    settings: Settings | None = None,
    *,
    runtime_factory: RuntimeFactory = create_runtime_services,
    auth_provider: AuthProvider | None = None,
) -> FastMCP:
    """Build an isolated server with a once-per-server runtime lifespan."""
    resolved_settings = settings or get_settings()
    set_level(resolved_settings.log_level)
    runtime_state = RuntimeState()
    server: FastMCP = FastMCP(
        "ModelArk Seed Multimodal",
        instructions=(
            "BytePlus multimodal generation server. Provides Seed Audio, Seedream, "
            "and Seedance tools. Generated media is persisted as durable MCP resources."
        ),
        auth=auth_provider or build_auth_provider(resolved_settings),
        lifespan=build_lifespan(resolved_settings, runtime_factory, runtime_state),
        middleware=[MetricsMiddleware()],
    )

    @server.resource(
        "seed-media://artifacts/{artifact_id}",
        auth=component_auth(resolved_settings, "artifacts:read"),
    )
    async def get_artifact(artifact_id: str, ctx: Context) -> ResourceResult:
        """Return persisted media after canonical ID and ownership checks."""
        try:
            parsed_artifact_id = UUID(artifact_id, version=4)
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid artifact ID format: '{artifact_id}'") from exc
        if str(parsed_artifact_id) != artifact_id:
            raise ValueError(f"Invalid artifact ID format: '{artifact_id}'")

        runtime = get_runtime(ctx)
        artifact = await runtime.artifact_store.get(
            artifact_id,
            auth=get_principal(ctx),
        )
        log_info(
            "artifact_served",
            artifact_id=artifact_id,
            media_type=artifact.media_type,
            mime_type=artifact.mime_type,
            bytes=len(artifact.data),
        )
        return ResourceResult(
            contents=[ResourceContent(content=artifact.data, mime_type=artifact.mime_type)],
            meta={"artifact_id": artifact_id, "media_type": artifact.media_type},
        )

    @server.resource("seed-health://status")
    async def health_status() -> str:
        """Return a credential-free MCP health summary."""
        return (
            "ModelArk Seed MCP Server\n"
            "Status: healthy\n"
            f"ModelArk configured: {resolved_settings.has_modelark}\n"
            f"Seed Audio configured: {resolved_settings.has_seed_audio}\n"
            f"TOS configured: {resolved_settings.has_tos}\n"
            f"Artifact backend: {resolved_settings.artifact_backend}\n"
            f"Transport: {resolved_settings.mcp_transport}\n"
        )

    @server.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy"})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(_request: Request) -> JSONResponse:
        runtime = runtime_state.runtime
        if runtime is None:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        try:
            await runtime.ownership_store.ping()
            artifact_root = Path(runtime.settings.artifact_dir).expanduser().resolve()
            if not artifact_root.is_dir() or not os.access(artifact_root, os.W_OK):
                raise RuntimeError("Artifact storage is not writable.")
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})

    @server.custom_route("/metrics", methods=["GET"])
    async def metrics(_request: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    register_tools(server, resolved_settings)
    return server


mcp: FastMCP = create_server()
