from __future__ import annotations

import asyncio
import sys
import textwrap
from time import perf_counter

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp_tasks import call_tool_task


def _mock_server_transport(tmp_path) -> StdioTransport:
    script = tmp_path / "server.py"
    script.write_text(
        textwrap.dedent("""
        import asyncio
        from ark_mcp.config.env import Settings
        from ark_mcp.providers.modelark.schemas import ChatCompletionProviderResponse
        from ark_mcp.providers.modelark.understanding import SeedUnderstandingService
        from ark_mcp.server import create_server

        async def delayed_generate(self, request):
            await asyncio.sleep(2)
            return (
                ChatCompletionProviderResponse.model_validate({
                    "id": "stdio-test",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "stdio completed"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
                }),
                None,
            )

        SeedUnderstandingService.generate = delayed_generate
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
    return transport


@pytest.mark.asyncio
async def test_stdio_background_task_completes_with_mocked_provider(tmp_path):
    transport = _mock_server_transport(tmp_path)
    async with Client(transport) as client:
        task = await call_tool_task(client, "seed_understand", {"input": {"prompt": "Test"}})
        result = await asyncio.wait_for(task.result(), timeout=20)
        assert not result.is_error
        assert result.structured_content["choices"][0]["content"] == "stdio completed"


@pytest.mark.asyncio
async def test_stdio_legacy_client_completes_background_job(tmp_path):
    transport = _mock_server_transport(tmp_path)
    async with Client(transport, mode="legacy") as client:
        started = perf_counter()
        submitted = await client.call_tool(
            "ark_job_submit",
            {
                "input": {
                    "tool_name": "seed_understand",
                    "arguments": {"input": {"prompt": "Test"}},
                }
            },
        )
        assert perf_counter() - started < 1.5
        job_id = submitted.structured_content["job_id"]
        async with asyncio.timeout(20):
            while True:
                result = await client.call_tool(
                    "ark_job_get",
                    {"input": {"job_id": job_id}},
                )
                if result.structured_content["status"] != "working":
                    break
                await asyncio.sleep(0.01)

    assert result.structured_content["status"] == "completed"
    target_result = result.structured_content["result"]
    assert target_result["is_error"] is False
    assert target_result["structured_content"]["choices"][0]["content"] == "stdio completed"
