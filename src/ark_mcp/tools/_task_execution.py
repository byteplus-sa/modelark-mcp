"""Task-execution guards shared by optional background tools."""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult


async def context_log(
    ctx: Context, level: Literal["info", "warning", "error"], message: str
) -> None:
    """Send a client log when a live MCP session is available."""
    if getattr(ctx, "is_background_task", False):
        return
    await getattr(ctx, level)(message)


def persistence_requires_task(ctx: Context, persist_output: bool) -> ToolResult | None:
    """Reject foreground persistence while allowing foreground status polling."""
    if persist_output and not getattr(ctx, "task_id", None):
        return ToolResult(
            content=(
                "persist_output=true requires task-augmented execution; use "
                "persist_output=false for foreground status polling."
            ),
            is_error=True,
        )
    return None
