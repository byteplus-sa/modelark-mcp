"""Shared MCP client and legacy context helpers for standalone smoke scripts."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastmcp.tools import ToolResult
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from fastmcp import Client

    from ark_mcp.config.env import Settings
    from ark_mcp.runtime import RuntimeServices


@dataclass
class SmokeContext:
    """Capture handler diagnostics while supplying runtime lifecycle services."""

    messages: list[str] = field(default_factory=list)
    progress_reports: list[tuple[int, int]] = field(default_factory=list)
    lifespan_context: dict[str, Any] = field(default_factory=dict)

    async def info(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"INFO: {message}")

    async def debug(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"DEBUG: {message}")

    async def warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"WARNING: {message}")

    async def error(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"ERROR: {message}")

    async def report_progress(self, progress: int, total: int) -> None:
        self.progress_reports.append((progress, total))


def require_tool_success[T](result: T | ToolResult) -> T:
    """Unwrap a successful tool output or expose its normalized error.

    Direct handler invocation returns ``ToolResult`` for provider failures so
    an MCP client receives a structured ``isError`` response instead of a
    Python exception.  A smoke test must treat that result as a failure.
    """
    if isinstance(result, ToolResult):
        details = result.structured_content or {"content": result.content}
        raise RuntimeError(f"Tool returned an error result: {json.dumps(details, default=str)}")
    return result


@dataclass
class SmokeClient:
    """Run smoke workflows through the public MCP task protocol."""

    client: Client
    foreground_client: Client | None = None

    async def call[T: BaseModel](
        self, name: str, params: BaseModel, output_type: type[T], *, background: bool = True
    ) -> T:
        from fastmcp_tasks import call_tool_task

        arguments = {"input": params.model_dump(mode="json")}
        if background:
            task = await call_tool_task(self.client, name, arguments)
            print(f"  MCP task ID: {task.task_id}")
            result = await task.result()
        else:
            client = self.foreground_client or self.client
            result = await client.call_tool(name, arguments)
        return output_type.model_validate(result.structured_content)

    def save_provider_ids(self, directory: Path, task_ids: list[str]) -> None:
        import os
        from datetime import UTC, datetime

        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "smoke_provider_tasks.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "created_at": datetime.now(UTC).isoformat(),
                        "provider": "seedance",
                        "task_ids": task_ids,
                    }
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())


@asynccontextmanager
async def smoke_session(settings: Settings) -> AsyncIterator[tuple[SmokeClient, RuntimeServices]]:
    """Own one real server lifespan and expose its artifact store to the scripts."""
    from fastmcp import Client

    from ark_mcp.runtime import create_runtime_services
    from ark_mcp.server import create_server

    runtime: RuntimeServices | None = None

    async def runtime_factory(resolved_settings: Settings) -> RuntimeServices:
        nonlocal runtime
        runtime = await create_runtime_services(resolved_settings)
        return runtime

    server = create_server(settings, runtime_factory=runtime_factory)
    async with Client(server) as client, Client(server, mode="legacy") as foreground_client:
        assert runtime is not None
        yield SmokeClient(client, foreground_client), runtime
