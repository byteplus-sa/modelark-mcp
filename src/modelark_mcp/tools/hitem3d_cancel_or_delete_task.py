"""``hitem3d_cancel_or_delete_task`` tool — cancel or delete a Hitem3d task."""

from __future__ import annotations

from fastmcp import Context
from fastmcp.tools import ToolResult

from modelark_mcp.tools._seed3d_shared import (
    Seed3DCancelOrDeleteInput,
    Seed3DCancelOrDeleteOutput,
    seed3d_cancel_or_delete_impl,
)


async def hitem3d_cancel_or_delete_task(
    input: Seed3DCancelOrDeleteInput, ctx: Context
) -> Seed3DCancelOrDeleteOutput | ToolResult:
    """Cancel (queued) or delete (terminal) a Hitem3d 3D generation task.

    - **cancel**: Stops a queued task; it transitions to ``cancelled``.
    - **delete**: Permanently removes the record of a succeeded, failed, or
      expired task.

    The handler verifies the actual status matches ``expected_status``
    before acting, preventing accidental cancellation or deletion.
    """
    return await seed3d_cancel_or_delete_impl(input, ctx, "hitem3d")


TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}
