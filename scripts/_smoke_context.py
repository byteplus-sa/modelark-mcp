"""Minimal FastMCP context adapter used by the live smoke-test scripts.

The scripts execute outside pytest, so they must not depend on test-only modules.
Tool handlers only require the small logging/progress surface implemented here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fastmcp.tools import ToolResult


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
