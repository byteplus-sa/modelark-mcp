"""FastMCP server factory and module-level deployment entrypoint.

Implements ``plans/PLAN_CODEBASE_GAP_REMEDIATION.md``. Runtime resources are
created once by the FastMCP lifespan; importing this module only assembles the
declarative server surface.
"""

from __future__ import annotations

import contextlib
import os
import subprocess  # nosec B404
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import truststore

truststore.inject_into_ssl()

from fastmcp import Context, FastMCP  # noqa: E402
from fastmcp.resources import ResourceContent, ResourceResult  # noqa: E402
from fastmcp.server.tasks import TaskConfig  # noqa: E402
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
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
from modelark_mcp.security.http_middleware import (  # noqa: E402
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
)

_REQUIRED_BACKGROUND_TASK_NAMES = frozenset(
    {
        "media_upload",
        "seed_audio_generate",
        "seed_audio_generate_variations",
        "speech_to_text",
        "seed_understand",
        "seedream_generate_image",
        "seedream_edit_image",
        "seedream_generate_image_variations",
        "seedance_create_task",
        "seedance_create_task_variations",
        "seedance_2_5_create_task",
        "seedance_2_5_create_task_variations",
        "hyper3d_create_task",
        "hitem3d_create_task",
        "vod_enhance_video",
        "vod_transcode_video",
        "vod_separate_audio",
        "vod_add_subtitles",
        "vod_remove_subtitles",
    }
)
_OPTIONAL_BACKGROUND_TASK_NAMES = frozenset(
    {
        "seedance_get_task",
        "hyper3d_get_task",
        "hitem3d_get_task",
        "vod_get_enhancement_task",
        "vod_get_transcode_task",
        "vod_get_audio_separation",
        "vod_get_subtitle_addition_task",
        "vod_get_subtitle_removal_task",
    }
)
_BACKGROUND_TASK_POLL_INTERVAL = timedelta(seconds=2)


def _task_config(tool_name: str) -> TaskConfig | None:
    if tool_name in _REQUIRED_BACKGROUND_TASK_NAMES:
        return TaskConfig(mode="required", poll_interval=_BACKGROUND_TASK_POLL_INTERVAL)
    if tool_name in _OPTIONAL_BACKGROUND_TASK_NAMES:
        return TaskConfig(mode="optional", poll_interval=_BACKGROUND_TASK_POLL_INTERVAL)
    return None


def register_tools(server: FastMCP, settings: Settings) -> None:
    """Register configured tools on one server instance."""

    from modelark_mcp.tools.seed_media_get_artifact import (
        TOOL_ANNOTATIONS as get_artifact_annotations,
    )
    from modelark_mcp.tools.seed_media_get_artifact import (
        SeedMediaGetArtifactOutput,
        seed_media_get_artifact,
    )

    server.tool(
        name="seed_media_get_artifact",
        annotations={**get_artifact_annotations},
        output_schema=SeedMediaGetArtifactOutput.model_json_schema(),
        auth=component_auth(settings, "artifacts:read"),
    )(seed_media_get_artifact)

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
            task=_task_config("seed_audio_generate"),
            auth=component_auth(settings, "seed:audio:generate"),
        )(seed_audio_generate)
        server.tool(
            name="seed_audio_generate_variations",
            annotations={**audio_var_annotations},
            output_schema=SeedAudioVariationsOutput.model_json_schema(),
            task=_task_config("seed_audio_generate_variations"),
            auth=component_auth(settings, "seed:audio:generate"),
        )(seed_audio_generate_variations)

    if settings.has_object_storage:
        from modelark_mcp.tools.media_presign import (
            TOOL_ANNOTATIONS as presign_annotations,
        )
        from modelark_mcp.tools.media_presign import (
            MediaPresignOutput,
            media_presign,
        )
        from modelark_mcp.tools.media_presign_batch import (
            TOOL_ANNOTATIONS as presign_batch_annotations,
        )
        from modelark_mcp.tools.media_presign_batch import (
            MediaPresignBatchOutput,
            media_presign_batch,
        )
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
            task=_task_config("media_upload"),
            auth=component_auth(settings, "media:upload"),
        )(media_upload)
        server.tool(
            name="media_presign",
            annotations={**presign_annotations},
            output_schema=MediaPresignOutput.model_json_schema(),
            auth=component_auth(settings, "media:presign"),
        )(media_presign)
        server.tool(
            name="media_presign_batch",
            annotations={**presign_batch_annotations},
            output_schema=MediaPresignBatchOutput.model_json_schema(),
            auth=component_auth(settings, "media:presign"),
        )(media_presign_batch)

    if settings.has_stt:
        from modelark_mcp.tools.speech_to_text import (
            TOOL_ANNOTATIONS as stt_annotations,
        )
        from modelark_mcp.tools.speech_to_text import (
            SpeechToTextOutput,
            speech_to_text,
        )

        server.tool(
            name="speech_to_text",
            annotations={**stt_annotations},
            output_schema=SpeechToTextOutput.model_json_schema(),
            task=_task_config("speech_to_text"),
            auth=component_auth(settings, "seed:asr:transcribe"),
        )(speech_to_text)

    if settings.has_vod_mediakit:
        from modelark_mcp.tools.vod_add_subtitles import (
            TOOL_ANNOTATIONS as vod_add_subtitles_annotations,
        )
        from modelark_mcp.tools.vod_add_subtitles import (
            VodAddSubtitlesOutput,
            vod_add_subtitles,
        )
        from modelark_mcp.tools.vod_enhance_video import (
            TOOL_ANNOTATIONS as vod_enhance_annotations,
        )
        from modelark_mcp.tools.vod_enhance_video import (
            VodEnhanceVideoOutput,
            vod_enhance_video,
        )
        from modelark_mcp.tools.vod_get_audio_separation import (
            TOOL_ANNOTATIONS as vod_get_audio_separation_annotations,
        )
        from modelark_mcp.tools.vod_get_audio_separation import (
            VodAudioSeparationTaskOutput,
            vod_get_audio_separation,
        )
        from modelark_mcp.tools.vod_get_enhancement_task import (
            TOOL_ANNOTATIONS as vod_get_enhancement_annotations,
        )
        from modelark_mcp.tools.vod_get_enhancement_task import (
            VodEnhancementTaskOutput,
            vod_get_enhancement_task,
        )
        from modelark_mcp.tools.vod_get_subtitle_addition_task import (
            TOOL_ANNOTATIONS as vod_get_subtitle_addition_annotations,
        )
        from modelark_mcp.tools.vod_get_subtitle_addition_task import (
            VodSubtitleAdditionTaskOutput,
            vod_get_subtitle_addition_task,
        )
        from modelark_mcp.tools.vod_get_subtitle_removal_task import (
            TOOL_ANNOTATIONS as vod_get_subtitle_removal_annotations,
        )
        from modelark_mcp.tools.vod_get_subtitle_removal_task import (
            VodSubtitleRemovalTaskOutput,
            vod_get_subtitle_removal_task,
        )
        from modelark_mcp.tools.vod_get_transcode_task import (
            TOOL_ANNOTATIONS as vod_get_transcode_annotations,
        )
        from modelark_mcp.tools.vod_get_transcode_task import (
            VodTranscodeTaskOutput,
            vod_get_transcode_task,
        )
        from modelark_mcp.tools.vod_remove_subtitles import (
            TOOL_ANNOTATIONS as vod_remove_subtitles_annotations,
        )
        from modelark_mcp.tools.vod_remove_subtitles import (
            VodRemoveSubtitlesOutput,
            vod_remove_subtitles,
        )
        from modelark_mcp.tools.vod_separate_audio import (
            TOOL_ANNOTATIONS as vod_separate_audio_annotations,
        )
        from modelark_mcp.tools.vod_separate_audio import (
            VodSeparateAudioOutput,
            vod_separate_audio,
        )
        from modelark_mcp.tools.vod_transcode_video import (
            TOOL_ANNOTATIONS as vod_transcode_annotations,
        )
        from modelark_mcp.tools.vod_transcode_video import (
            VodTranscodeVideoOutput,
            vod_transcode_video,
        )

        server.tool(
            name="vod_enhance_video",
            annotations={**vod_enhance_annotations},
            output_schema=VodEnhanceVideoOutput.model_json_schema(),
            task=_task_config("vod_enhance_video"),
            auth=component_auth(settings, "vod:enhance"),
        )(vod_enhance_video)
        server.tool(
            name="vod_get_enhancement_task",
            annotations={**vod_get_enhancement_annotations},
            output_schema=VodEnhancementTaskOutput.model_json_schema(),
            task=_task_config("vod_get_enhancement_task"),
            auth=component_auth(settings, "vod:read"),
        )(vod_get_enhancement_task)
        server.tool(
            name="vod_transcode_video",
            annotations={**vod_transcode_annotations},
            output_schema=VodTranscodeVideoOutput.model_json_schema(),
            task=_task_config("vod_transcode_video"),
            auth=component_auth(settings, "vod:transcode"),
        )(vod_transcode_video)
        server.tool(
            name="vod_get_transcode_task",
            annotations={**vod_get_transcode_annotations},
            output_schema=VodTranscodeTaskOutput.model_json_schema(),
            task=_task_config("vod_get_transcode_task"),
            auth=component_auth(settings, "vod:read"),
        )(vod_get_transcode_task)
        server.tool(
            name="vod_separate_audio",
            annotations={**vod_separate_audio_annotations},
            output_schema=VodSeparateAudioOutput.model_json_schema(),
            task=_task_config("vod_separate_audio"),
            auth=component_auth(settings, "vod:extract"),
        )(vod_separate_audio)
        server.tool(
            name="vod_get_audio_separation",
            annotations={**vod_get_audio_separation_annotations},
            output_schema=VodAudioSeparationTaskOutput.model_json_schema(),
            task=_task_config("vod_get_audio_separation"),
            auth=component_auth(settings, "vod:read"),
        )(vod_get_audio_separation)
        server.tool(
            name="vod_add_subtitles",
            annotations={**vod_add_subtitles_annotations},
            output_schema=VodAddSubtitlesOutput.model_json_schema(),
            task=_task_config("vod_add_subtitles"),
            auth=component_auth(settings, "vod:subtitle:add"),
        )(vod_add_subtitles)
        server.tool(
            name="vod_get_subtitle_addition_task",
            annotations={**vod_get_subtitle_addition_annotations},
            output_schema=VodSubtitleAdditionTaskOutput.model_json_schema(),
            task=_task_config("vod_get_subtitle_addition_task"),
            auth=component_auth(settings, "vod:read"),
        )(vod_get_subtitle_addition_task)
        server.tool(
            name="vod_remove_subtitles",
            annotations={**vod_remove_subtitles_annotations},
            output_schema=VodRemoveSubtitlesOutput.model_json_schema(),
            task=_task_config("vod_remove_subtitles"),
            auth=component_auth(settings, "vod:subtitle:remove"),
        )(vod_remove_subtitles)
        server.tool(
            name="vod_get_subtitle_removal_task",
            annotations={**vod_get_subtitle_removal_annotations},
            output_schema=VodSubtitleRemovalTaskOutput.model_json_schema(),
            task=_task_config("vod_get_subtitle_removal_task"),
            auth=component_auth(settings, "vod:read"),
        )(vod_get_subtitle_removal_task)

    if not settings.has_modelark:
        log_info("tools_skipped", reason="BYTEPLUS_MODELARK_API_KEY not configured")
        return

    from modelark_mcp.tools.seed_understand import (
        TOOL_ANNOTATIONS as understand_annotations,
    )
    from modelark_mcp.tools.seed_understand import (
        SeedUnderstandOutput,
        seed_understand,
    )
    from modelark_mcp.tools.seedance_2_5_create_task import (
        TOOL_ANNOTATIONS as create_2_5_annotations,
    )
    from modelark_mcp.tools.seedance_2_5_create_task import (
        Seedance25CreateTaskOutput,
        seedance_2_5_create_task,
    )
    from modelark_mcp.tools.seedance_2_5_create_task_variations import (
        TOOL_ANNOTATIONS as seedance_2_5_var_annotations,
    )
    from modelark_mcp.tools.seedance_2_5_create_task_variations import (
        Seedance25VariationsOutput,
        seedance_2_5_create_task_variations,
    )
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
    from modelark_mcp.tools.seedream_edit_image import (
        TOOL_ANNOTATIONS as seedream_edit_annotations,
    )
    from modelark_mcp.tools.seedream_edit_image import (
        SeedreamEditOutput,
        seedream_edit_image,
    )
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
            "seedream_edit_image",
            seedream_edit_annotations,
            SeedreamEditOutput,
            "seedream:generate",
            seedream_edit_image,
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
            "seedance_2_5_create_task",
            create_2_5_annotations,
            Seedance25CreateTaskOutput,
            "seedance:create",
            seedance_2_5_create_task,
        ),
        (
            "seedance_2_5_create_task_variations",
            seedance_2_5_var_annotations,
            Seedance25VariationsOutput,
            "seedance:create",
            seedance_2_5_create_task_variations,
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
        (
            "seed_understand",
            understand_annotations,
            SeedUnderstandOutput,
            "understanding:read",
            seed_understand,
        ),
    )
    for name, tool_annotations, output_model, scope, handler in registrations:
        server.tool(
            name=name,
            annotations={**tool_annotations},
            output_schema=output_model.model_json_schema(),
            task=_task_config(name),
            auth=component_auth(settings, scope),
        )(handler)

    if settings.has_seed3d:
        from modelark_mcp.tools._seed3d_shared import (
            Seed3DCancelOrDeleteOutput,
            Seed3DCreateTaskOutput,
            Seed3DTaskOutput,
            Seed3DTaskPage,
        )
        from modelark_mcp.tools.hitem3d_cancel_or_delete_task import (
            TOOL_ANNOTATIONS as hitem3d_cancel_annotations,
        )
        from modelark_mcp.tools.hitem3d_cancel_or_delete_task import (
            hitem3d_cancel_or_delete_task,
        )
        from modelark_mcp.tools.hitem3d_create_task import (
            TOOL_ANNOTATIONS as hitem3d_create_annotations,
        )
        from modelark_mcp.tools.hitem3d_create_task import hitem3d_create_task
        from modelark_mcp.tools.hitem3d_get_task import (
            TOOL_ANNOTATIONS as hitem3d_get_annotations,
        )
        from modelark_mcp.tools.hitem3d_get_task import hitem3d_get_task
        from modelark_mcp.tools.hitem3d_list_tasks import (
            TOOL_ANNOTATIONS as hitem3d_list_annotations,
        )
        from modelark_mcp.tools.hitem3d_list_tasks import hitem3d_list_tasks
        from modelark_mcp.tools.hyper3d_cancel_or_delete_task import (
            TOOL_ANNOTATIONS as hyper3d_cancel_annotations,
        )
        from modelark_mcp.tools.hyper3d_cancel_or_delete_task import (
            hyper3d_cancel_or_delete_task,
        )
        from modelark_mcp.tools.hyper3d_create_task import (
            TOOL_ANNOTATIONS as hyper3d_create_annotations,
        )
        from modelark_mcp.tools.hyper3d_create_task import hyper3d_create_task
        from modelark_mcp.tools.hyper3d_get_task import (
            TOOL_ANNOTATIONS as hyper3d_get_annotations,
        )
        from modelark_mcp.tools.hyper3d_get_task import hyper3d_get_task
        from modelark_mcp.tools.hyper3d_list_tasks import (
            TOOL_ANNOTATIONS as hyper3d_list_annotations,
        )
        from modelark_mcp.tools.hyper3d_list_tasks import hyper3d_list_tasks

        seed3d_registrations = (
            (
                "hyper3d_create_task",
                hyper3d_create_annotations,
                Seed3DCreateTaskOutput,
                "hyper3d:create",
                hyper3d_create_task,
            ),
            (
                "hyper3d_get_task",
                hyper3d_get_annotations,
                Seed3DTaskOutput,
                "hyper3d:read",
                hyper3d_get_task,
            ),
            (
                "hyper3d_list_tasks",
                hyper3d_list_annotations,
                Seed3DTaskPage,
                "hyper3d:read",
                hyper3d_list_tasks,
            ),
            (
                "hyper3d_cancel_or_delete_task",
                hyper3d_cancel_annotations,
                Seed3DCancelOrDeleteOutput,
                "hyper3d:delete",
                hyper3d_cancel_or_delete_task,
            ),
            (
                "hitem3d_create_task",
                hitem3d_create_annotations,
                Seed3DCreateTaskOutput,
                "hitem3d:create",
                hitem3d_create_task,
            ),
            (
                "hitem3d_get_task",
                hitem3d_get_annotations,
                Seed3DTaskOutput,
                "hitem3d:read",
                hitem3d_get_task,
            ),
            (
                "hitem3d_list_tasks",
                hitem3d_list_annotations,
                Seed3DTaskPage,
                "hitem3d:read",
                hitem3d_list_tasks,
            ),
            (
                "hitem3d_cancel_or_delete_task",
                hitem3d_cancel_annotations,
                Seed3DCancelOrDeleteOutput,
                "hitem3d:delete",
                hitem3d_cancel_or_delete_task,
            ),
        )
        for (
            seed3d_name,
            seed3d_annotations,
            seed3d_output_model,
            seed3d_scope,
            seed3d_handler,
        ) in seed3d_registrations:
            server.tool(
                name=seed3d_name,
                annotations={**seed3d_annotations},
                output_schema=seed3d_output_model.model_json_schema(),
                task=_task_config(seed3d_name),
                auth=component_auth(settings, seed3d_scope),
            )(seed3d_handler)


class HardenedFastMCP(FastMCP):
    """FastMCP subclass that applies ASGI body and rate-limit middleware for HTTP."""

    def __init__(
        self,
        *args: Any,
        app_settings: Settings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._app_settings = app_settings

    def http_app(self, *args: Any, **kwargs: Any) -> Any:
        if self._app_settings is not None and self._app_settings.mcp_transport == "http":
            asgi_middleware = [
                Middleware(
                    RequestBodyLimitMiddleware,
                    max_bytes=self._app_settings.mcp_http_max_body_bytes,
                ),
            ]
            if self._app_settings.rate_limit_rpm > 0:
                asgi_middleware.append(
                    Middleware(
                        RateLimitMiddleware,
                        rpm=self._app_settings.rate_limit_rpm,
                        burst=(
                            self._app_settings.rate_limit_burst or self._app_settings.rate_limit_rpm
                        ),
                        trust_proxy_headers=self._app_settings.rate_limit_trust_proxy_headers,
                    )
                )
            asgi_middleware.extend(kwargs.get("middleware") or [])
            kwargs["middleware"] = asgi_middleware
        return super().http_app(*args, **kwargs)


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
    server: FastMCP = HardenedFastMCP(
        "ModelArk Seed Multimodal",
        instructions=(
            "BytePlus multimodal generation server. Provides Seed Audio, Seedream, "
            "Seedance, Seed 2.1 multimodal understanding, and Speech-to-Text tools. "
            "BytePlus VOD AI MediaKit enhancement, video transcoding, subtitle burn-in, "
            "subtitle or text removal, and voice and background audio separation are "
            "available when the MediaKit API key is "
            "configured. Generated media is persisted as durable MCP resources."
        ),
        auth=auth_provider or build_auth_provider(resolved_settings),
        lifespan=build_lifespan(resolved_settings, runtime_factory, runtime_state),
        middleware=[MetricsMiddleware()],
        app_settings=resolved_settings,
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
        stamp = _build_stamp()
        return (
            "ModelArk Seed MCP Server\n"
            f"Build: {stamp}\n"
            "Status: healthy\n"
            f"ModelArk configured: {resolved_settings.has_modelark}\n"
            f"Seed 3D configured: {resolved_settings.has_seed3d}\n"
            f"Seed Audio configured: {resolved_settings.has_seed_audio}\n"
            f"VOD AI MediaKit configured: {resolved_settings.has_vod_mediakit}\n"
            f"TOS configured: {resolved_settings.has_tos}\n"
            f"S3 configured: {resolved_settings.has_s3}\n"
            f"Object storage backend: {resolved_settings.object_storage_backend}\n"
            f"STT configured: {resolved_settings.has_stt}\n"
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

        if not resolved_settings.readiness_check_providers:
            return JSONResponse({"status": "ready"})

        providers: dict[str, str] = {}
        timeout = resolved_settings.readiness_provider_timeout_seconds

        if resolved_settings.has_modelark:
            from modelark_mcp.providers.modelark.client import ModelArkGateway

            modelark_gw = ModelArkGateway(
                api_key=resolved_settings.modelark_api_key,
                base_url=resolved_settings.modelark_base_url,
                timeout=resolved_settings.request_timeout_ms / 1000,
                connect_timeout=resolved_settings.connect_timeout_ms / 1000,
            )
            try:
                providers["modelark"] = (
                    "reachable"
                    if await modelark_gw.health_check(timeout_seconds=timeout)
                    else "unreachable"
                )
            finally:
                await modelark_gw.close()

        if resolved_settings.has_seed_audio:
            from modelark_mcp.providers.seed_speech.client import SeedSpeechGateway

            audio_gw = SeedSpeechGateway(
                api_key=resolved_settings.seed_speech_api_key,
                base_url=resolved_settings.seed_audio_base_url,
                timeout=resolved_settings.request_timeout_ms / 1000,
                connect_timeout=resolved_settings.connect_timeout_ms / 1000,
            )
            try:
                providers["seed_audio"] = (
                    "reachable"
                    if await audio_gw.health_check(timeout_seconds=timeout)
                    else "unreachable"
                )
            finally:
                await audio_gw.close()

        if resolved_settings.has_stt:
            from modelark_mcp.providers.seed_speech.asr_http import SeedSpeechAsrHttpGateway

            stt_gw = SeedSpeechAsrHttpGateway(
                api_key=resolved_settings.seed_speech_api_key,
                base_url=resolved_settings.seed_speech_asr_base_url,
                timeout=resolved_settings.request_timeout_ms / 1000,
                connect_timeout=resolved_settings.connect_timeout_ms / 1000,
            )
            try:
                providers["stt"] = (
                    "reachable"
                    if await stt_gw.health_check(timeout_seconds=timeout)
                    else "unreachable"
                )
            finally:
                await stt_gw.close()

        if resolved_settings.has_vod_mediakit:
            from modelark_mcp.providers.vod_mediakit.client import VodMediaKitGateway

            vod_gw = VodMediaKitGateway(
                api_key=resolved_settings.vod_mediakit_api_key,
                base_url=resolved_settings.vod_mediakit_base_url,
                timeout=resolved_settings.request_timeout_ms / 1000,
                connect_timeout=resolved_settings.connect_timeout_ms / 1000,
            )
            try:
                providers["vod_mediakit"] = (
                    "reachable"
                    if await vod_gw.health_check(timeout_seconds=timeout)
                    else "unreachable"
                )
            finally:
                await vod_gw.close()

        all_reachable = all(v == "reachable" for v in providers.values())
        if all_reachable:
            return JSONResponse({"status": "ready", "providers": providers})
        return JSONResponse(
            {"status": "degraded", "providers": providers},
            status_code=503,
        )

    @server.custom_route("/metrics", methods=["GET"])
    async def metrics(_request: Request) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    register_tools(server, resolved_settings)
    log_info(
        "server_ready",
        transport=resolved_settings.mcp_transport,
        auth_mode=resolved_settings.mcp_auth_mode.value,
        modelark_configured=resolved_settings.has_modelark,
        seed_audio_configured=resolved_settings.has_seed_audio,
        seed3d_configured=resolved_settings.has_seed3d,
        stt_configured=resolved_settings.has_stt,
        vod_mediakit_configured=resolved_settings.has_vod_mediakit,
        object_storage_backend=resolved_settings.object_storage_backend,
        artifact_backend=resolved_settings.artifact_backend,
        log_level=resolved_settings.log_level,
    )
    return server


mcp: FastMCP = create_server()


def _build_stamp() -> str:
    """Return a short build-identity stamp (git SHA + import time)."""
    sha = _git_sha()
    installed = datetime.now(UTC).isoformat()
    if sha:
        return f"git:{sha} installed:{installed}"
    return f"installed:{installed}"


def _git_sha() -> str | None:
    """Return the short (7-char) git SHA of HEAD, or None on failure."""
    with contextlib.suppress(Exception):
        result = subprocess.run(  # nosec B603, B607
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return None
