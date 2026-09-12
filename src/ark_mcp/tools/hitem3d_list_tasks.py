"""``hitem3d_list_tasks`` tool — list recent Hitem3d 3D generation tasks."""

from __future__ import annotations

from fastmcp import Context
from fastmcp.tools import ToolResult

from ark_mcp.tools._seed3d_shared import (
    Seed3DListTasksInput,
    Seed3DTaskPage,
    seed3d_list_tasks_impl,
)


async def hitem3d_list_tasks(
    input: Seed3DListTasksInput, ctx: Context
) -> Seed3DTaskPage | ToolResult:
    """List recent Hitem3d 3D generation tasks.

    Queries the previous seven days of tasks (provider limitation).
    Supports filtering by status, task IDs, and model.
    """
    return await seed3d_list_tasks_impl(input, ctx, "hitem3d")


TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
