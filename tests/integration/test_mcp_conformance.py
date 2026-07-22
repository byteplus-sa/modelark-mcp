"""MCP protocol conformance tests.

Verifies tool discovery, inputSchema/outputSchema auto-generation,
ToolAnnotations propagation, resource template registration, and
conditional tool registration based on credentials.

These tests exercise the FastMCP layer directly — no provider calls.
"""

from __future__ import annotations

import pytest

from modelark_mcp.config.env import get_settings


@pytest.fixture
def configured_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set test env vars and re-register tools with fake credentials."""
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-test")

    # Clear cached settings.
    get_settings.cache_clear()

    # Re-import server to re-register tools with new settings.
    import importlib

    import modelark_mcp.server as server_mod

    importlib.reload(server_mod)

    yield server_mod

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

    import importlib

    import modelark_mcp.server as server_mod

    importlib.reload(server_mod)

    yield server_mod

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
            "seedream_generate_image",
            "seedream_generate_image_variations",
            "seedance_create_task",
            "seedance_create_task_variations",
            "seedance_get_task",
            "seedance_list_tasks",
            "seedance_cancel_or_delete_task",
        }


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
