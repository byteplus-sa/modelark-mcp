"""Task-execution guards shared by optional background tools."""

from __future__ import annotations

from fastmcp import Context
from fastmcp.tools import ToolResult


def persistence_requires_task(ctx: Context, persist_output: bool) -> ToolResult | None:
    """Reject foreground persistence while allowing foreground status polling."""
    if persist_output and getattr(ctx, "task_id", None) is None:
        return ToolResult(
            content=(
                "persist_output=true requires task-augmented execution; use "
                "persist_output=false for foreground status polling."
            ),
            is_error=True,
        )
    return None
