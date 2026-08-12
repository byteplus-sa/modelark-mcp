"""MCP protocol conformance tests.

Verifies tool discovery, inputSchema/outputSchema auto-generation,
ToolAnnotations propagation, resource template registration, and
conditional tool registration based on credentials.

These tests exercise the FastMCP layer directly — no provider calls.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modelark_mcp.config.env import Settings, get_settings
from modelark_mcp.server import create_server


@pytest.fixture
def configured_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set test env vars and re-register tools with fake credentials."""
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-test")
    monkeypatch.setenv("BYTEPLUS_VOD_MEDIAKIT_API_KEY", "test-mediakit-key")
    monkeypatch.setenv("SEED_SPEECH_ASR_API_KEY", "sk-test-asr")
    monkeypatch.setenv("TOS_ACCESS_KEY", "ak-test-tos")
    monkeypatch.setenv("TOS_SECRET_KEY", "sk-test-tos")
    monkeypatch.setenv("TOS_BUCKET", "test-bucket")

    # Clear cached settings.
    get_settings.cache_clear()

    yield SimpleNamespace(mcp=create_server(get_settings()))

    get_settings.cache_clear()


@pytest.fixture
def no_creds_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure server with no API keys set."""
    monkeypatch.delenv("BYTEPLUS_MODELARK_API_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SEED_AUDIO_API_KEY", raising=False)
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "")

    get_settings.cache_clear()

    yield SimpleNamespace(
        mcp=create_server(
            Settings(
                _env_file=None,
                BYTEPLUS_MODELARK_API_KEY="",
                BYTEPLUS_SEED_AUDIO_API_KEY="",
                BYTEPLUS_VOD_MEDIAKIT_API_KEY="",
            )
        )
    )

    get_settings.cache_clear()


@pytest.fixture
def s3_only_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure server with S3-only object storage creds."""
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-test")
    monkeypatch.setenv("SEED_SPEECH_ASR_API_KEY", "sk-test-asr")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak-s3-test")
    monkeypatch.setenv("S3_SECRET_KEY", "sk-s3-test")
    monkeypatch.setenv("S3_BUCKET", "test-s3-bucket")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "s3")

    get_settings.cache_clear()

    yield SimpleNamespace(mcp=create_server(get_settings()))

    get_settings.cache_clear()


class TestToolDiscovery:
    """Verify all six tools are discoverable when credentials are set."""

    async def test_all_tools_registered(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "seed_audio_generate",
            "seed_audio_generate_variations",
            "seed_media_get_artifact",
            "seedream_edit_image",
            "seedream_generate_image",
            "seedream_generate_image_variations",
            "seedance_create_task",
            "seedance_create_task_variations",
            "seedance_2_5_create_task",
            "seedance_2_5_create_task_variations",
            "seedance_get_task",
            "seedance_list_tasks",
            "seedance_cancel_or_delete_task",
            "seed_understand",
            "speech_to_text",
            "media_upload",
            "media_presign",
            "vod_enhance_video",
        }

    async def test_vod_mediakit_tool_not_registered_without_its_key(
        self, no_creds_server: None
    ) -> None:
        tools = await no_creds_server.mcp.list_tools()
        assert "vod_enhance_video" not in {tool.name for tool in tools}

    async def test_media_upload_registered_with_s3_only(self, s3_only_server: None) -> None:
        server = s3_only_server
        tools = await server.mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert "media_upload" in tool_names
        assert "media_presign" in tool_names


class TestToolAnnotations:
    """Verify ToolAnnotations are correctly propagated."""

    async def test_seed_audio_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seed_audio_generate")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is False
        assert tool.annotations.openWorldHint is True

    async def test_seedream_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.openWorldHint is True

    async def test_seedance_create_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.openWorldHint is True

    async def test_seedance_get_readonly(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_get_task")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.idempotentHint is True

    async def test_seedance_list_readonly(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_list_tasks")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.idempotentHint is True

    async def test_seedance_cancel_destructive(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_cancel_or_delete_task")
        assert tool.annotations is not None
        assert tool.annotations.destructiveHint is True
        assert tool.annotations.readOnlyHint is False

    async def test_vod_enhance_annotations(self, configured_server: None) -> None:
        tools = await configured_server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "vod_enhance_video")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is False
        assert tool.annotations.openWorldHint is True


class TestInputSchemas:
    """Verify inputSchema is auto-generated for each tool."""

    async def test_seed_audio_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seed_audio_generate")
        schema = tool.parameters
        assert schema is not None
        assert "properties" in schema
        assert "text_prompt" in schema["properties"]["input"]["properties"]
        assert schema["properties"]["input"]["required"] == ["text_prompt"]

    async def test_seedream_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image")
        schema = tool.parameters
        assert schema is not None
        assert "prompt" in schema["properties"]["input"]["properties"]
        assert schema["properties"]["input"]["required"] == ["prompt"]

    async def test_seedance_create_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task")
        schema = tool.parameters
        assert schema is not None
        assert "properties" in schema

    async def test_seedance_get_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_get_task")
        schema = tool.parameters
        assert schema is not None
        assert "task_id" in schema["properties"]["input"]["properties"]
        assert schema["properties"]["input"]["required"] == ["task_id"]

    async def test_seedance_cancel_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_cancel_or_delete_task")
        schema = tool.parameters
        assert schema is not None
        input_props = schema["properties"]["input"]["properties"]
        assert "task_id" in input_props
        assert "mode" in input_props
        assert "expected_status" in input_props
        assert "confirm" in input_props

    async def test_vod_enhance_schema_is_self_describing(self, configured_server: None) -> None:
        tools = await configured_server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "vod_enhance_video")
        input_schema = tool.parameters["properties"]["input"]
        assert input_schema["required"] == ["video_url"]
        assert all("description" in field for field in input_schema["properties"].values())
        assert tool.output_schema is not None
        assert all(
            "description" in field or "$ref" in field
            for field in tool.output_schema["properties"].values()
        )


class TestOutputSchemas:
    """Verify outputSchema is auto-generated for each tool."""

    async def test_seedream_output_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image")
        schema = tool.output_schema
        assert schema is not None
        assert "properties" in schema
        assert "artifacts" in schema["properties"]
        assert "model" in schema["properties"]

    async def test_seedance_create_output_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task")
        schema = tool.output_schema
        assert schema is not None
        assert "task_id" in schema["properties"]


class TestVariationToolAnnotations:
    """Verify ToolAnnotations for the three variation tools."""

    async def test_seedream_variations_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image_variations")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is True

    async def test_seed_audio_variations_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seed_audio_generate_variations")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.openWorldHint is True

    async def test_seedance_variations_annotations(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task_variations")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.openWorldHint is True


class TestVariationInputSchemas:
    """Verify inputSchema is auto-generated for variation tools."""

    async def test_seedream_variations_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image_variations")
        schema = tool.parameters
        assert schema is not None
        input_props = schema["properties"]["input"]["properties"]
        assert "prompt" in input_props
        assert "variations" in input_props
        assert "base_seed" in input_props

    async def test_seed_audio_variations_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seed_audio_generate_variations")
        schema = tool.parameters
        assert schema is not None
        input_props = schema["properties"]["input"]["properties"]
        assert "text_prompt" in input_props
        assert "variations" in input_props

    async def test_seedance_variations_input_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task_variations")
        schema = tool.parameters
        assert schema is not None
        input_props = schema["properties"]["input"]["properties"]
        assert "variations" in input_props
        assert "variation_prompts" in input_props


class TestVariationOutputSchemas:
    """Verify outputSchema is auto-generated for variation tools."""

    async def test_seedream_variations_output_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedream_generate_image_variations")
        schema = tool.output_schema
        assert schema is not None
        assert "summary" in schema["properties"]

    async def test_seed_audio_variations_output_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seed_audio_generate_variations")
        schema = tool.output_schema
        assert schema is not None
        assert "summary" in schema["properties"]

    async def test_seedance_variations_output_schema(self, configured_server: None) -> None:
        server = configured_server
        tools = await server.mcp.list_tools()
        tool = next(t for t in tools if t.name == "seedance_create_task_variations")
        schema = tool.output_schema
        assert schema is not None
        assert "summary" in schema["properties"]
        assert "recommended_poll_after_ms" in schema["properties"]


class TestResourceTemplate:
    """Verify the seed-media artifact resource template is registered."""

    async def test_resource_template_registered(self, configured_server: None) -> None:
        server = configured_server
        templates = await server.mcp.list_resource_templates()
        assert len(templates) >= 1
        artifact_tmpl = next(t for t in templates if "artifacts" in t.uri_template)
        assert "artifact_id" in artifact_tmpl.uri_template
        assert artifact_tmpl.name == "get_artifact"

    async def test_health_resource_registered(self, configured_server: None) -> None:
        server = configured_server
        resources = await server.mcp.list_resources()
        # Health resource is a static resource, not a template.
        assert len(resources) >= 1
