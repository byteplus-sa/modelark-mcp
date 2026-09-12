from __future__ import annotations

import asyncio
import sys
import textwrap

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp_tasks import call_tool_task


@pytest.mark.asyncio
async def test_stdio_background_task_completes_with_mocked_provider(tmp_path):
    script = tmp_path / "server.py"
    script.write_text(
        textwrap.dedent("""
        import asyncio
        from unittest.mock import AsyncMock
        from ark_mcp.config.env import Settings
        from ark_mcp.providers.modelark.schemas import ChatCompletionProviderResponse
        from ark_mcp.providers.modelark.understanding import SeedUnderstandingService
        from ark_mcp.server import create_server

        SeedUnderstandingService.generate = AsyncMock(return_value=(
            ChatCompletionProviderResponse.model_validate({
                "id": "stdio-test",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "stdio completed"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            }), None
        ))
        settings = Settings(_env_file=None, BYTEPLUS_MODELARK_API_KEY="test-key", artifact_dir="ARTIFACT_PATH")
        create_server(settings).run(transport="stdio", show_banner=False)
    """).replace("ARTIFACT_PATH", str(tmp_path / "artifacts"))
    )
    transport = StdioTransport(
        command=sys.executable,
        args=[str(script)],
        env={"BYTEPLUS_MODELARK_API_KEY": "test-key"},
        keep_alive=False,
    )
    async with Client(transport) as client:
        task = await call_tool_task(client, "seed_understand", {"input": {"prompt": "Test"}})
        result = await asyncio.wait_for(task.result(), timeout=20)
        assert not result.is_error
        assert result.structured_content["choices"][0]["content"] == "stdio completed"
