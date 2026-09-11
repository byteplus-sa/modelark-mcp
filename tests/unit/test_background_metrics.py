from __future__ import annotations

import asyncio
import inspect
from unittest.mock import Mock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.tools import ToolResult
from fastmcp_tasks import TasksExtension, call_tool_task

from modelark_mcp.observability import metrics


@pytest.fixture
def instruments(monkeypatch):
    counters = {
        name: Mock() for name in ("TOOL_REQUESTS", "TOOL_DURATION", "TOOL_ADMISSION_DURATION")
    }
    for name, counter in counters.items():
        monkeypatch.setattr(metrics, name, counter)
    return counters


@pytest.mark.parametrize("outcome", ["success", "error", "exception", "cancelled"])
async def test_real_worker_records_terminal_outcome_once(outcome, instruments):
    started = asyncio.Event()

    async def measured(value: int = 1) -> ToolResult:
        started.set()
        if outcome == "cancelled":
            await asyncio.Event().wait()
        await asyncio.sleep(0.06)
        if outcome == "exception":
            raise ValueError("pre-provider failure")
        return ToolResult(content=str(value), is_error=outcome == "error")

    wrapped = metrics.instrument_tool_execution(measured, tool_name="measured")
    assert inspect.signature(wrapped) == inspect.signature(measured, eval_str=True)
    server = FastMCP(middleware=[metrics.MetricsMiddleware()])
    server.add_extension(TasksExtension())
    server.tool(name="measured", task=True)(wrapped)
    async with Client(server) as client:
        task = await call_tool_task(client, "measured", {}, raise_on_error=False)
        await asyncio.wait_for(started.wait(), timeout=5)
        if outcome == "cancelled":
            await task.cancel()
            for _ in range(100):
                if instruments["TOOL_DURATION"].labels.return_value.observe.called:
                    break
                await asyncio.sleep(0.01)
        else:
            result = await task.result()
            assert result.is_error == (outcome in ("error", "exception"))
            await task.result()
            await task.status()
    labels = instruments["TOOL_REQUESTS"].labels.call_args_list
    assert [entry.kwargs["status"] for entry in labels].count("accepted") == 1
    assert [entry.kwargs["status"] for entry in labels].count(outcome) == 1
    instruments["TOOL_DURATION"].labels.return_value.observe.assert_called_once()
    if outcome != "cancelled":
        assert instruments["TOOL_DURATION"].labels.return_value.observe.call_args.args[0] >= 0.06
    instruments["TOOL_ADMISSION_DURATION"].labels.return_value.observe.assert_called_once()


async def test_foreground_wrapper_preserves_single_measurement(instruments):
    async def measured(value: int = 1) -> int:
        return value

    server = FastMCP(middleware=[metrics.MetricsMiddleware()])
    server.tool()(metrics.instrument_tool_execution(measured, tool_name="measured"))
    async with Client(server) as client:
        assert (await client.call_tool("measured", {"value": 9})).data == 9
    instruments["TOOL_REQUESTS"].labels.assert_called_once_with(tool="measured", status="success")
    instruments["TOOL_DURATION"].labels.return_value.observe.assert_called_once()
    instruments["TOOL_ADMISSION_DURATION"].labels.assert_not_called()


async def test_registered_server_worker_records_pre_provider_failure(
    instruments, monkeypatch, tmp_path
):
    from modelark_mcp.config.env import get_settings
    from modelark_mcp.config.model_capabilities import refresh_capability_registry
    from modelark_mcp.providers.modelark.understanding import SeedUnderstandingService
    from modelark_mcp.server import create_server

    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "test-placeholder")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ARTIFACT_BACKEND", "filesystem")
    get_settings.cache_clear()
    refresh_capability_registry()
    monkeypatch.setattr(
        SeedUnderstandingService,
        "build_request",
        Mock(side_effect=ValueError("pre-provider regression sentinel")),
    )
    try:
        server = create_server(get_settings())
        async with Client(server) as client:
            task = await call_tool_task(
                client,
                "seed_understand",
                {"input": {"prompt": "test"}},
                raise_on_error=False,
            )
            result = await task.result()
            assert result.is_error
            assert "pre-provider regression sentinel" in result.content[0].text
            await task.result()
            await task.status()
        labels = instruments["TOOL_REQUESTS"].labels.call_args_list
        assert sorted((entry.kwargs for entry in labels), key=lambda item: item["status"]) == [
            {"tool": "seed_understand", "status": "accepted"},
            {"tool": "seed_understand", "status": "exception"},
        ]
        instruments["TOOL_DURATION"].labels.return_value.observe.assert_called_once()
        instruments["TOOL_ADMISSION_DURATION"].labels.return_value.observe.assert_called_once()
    finally:
        get_settings.cache_clear()
        refresh_capability_registry()
