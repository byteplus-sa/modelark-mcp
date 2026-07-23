"""``seedance_list_tasks`` tool — list recent Seedance video generation tasks.

Queries only the previous seven days (provider limitation). The server
policy caps ``page_size`` at 100 even though the provider accepts 500,
avoiding oversized model context.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.domain.models import SeedanceTaskStatus, SeedanceTaskSummary
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.providers.modelark.seedance import SeedanceService
from modelark_mcp.providers.retry import call_with_retry
from modelark_mcp.runtime import get_principal, get_runtime
from modelark_mcp.tools._errors import provider_error_result


class SeedanceListTasksInput(BaseModel):
    """Input model for ``seedance_list_tasks``."""

    page: int | None = Field(None, ge=1, le=500)
    page_size: int | None = Field(None, ge=1, le=100)  # server policy caps at 100
    status: SeedanceTaskStatus | None = None
    task_ids: list[str] | None = None
    model: str | None = None
    service_tier: Literal["default", "flex"] | None = None


class SeedanceTaskPage(BaseModel):
    """Output model for ``seedance_list_tasks``."""

    tasks: list[SeedanceTaskSummary]
    total: int
    page: int
    page_size: int
    has_more: bool = False


async def seedance_list_tasks(
    input: SeedanceListTasksInput, ctx: Context
) -> SeedanceTaskPage | ToolResult:
    """List recent Seedance video generation tasks.

    Queries the previous seven days of tasks (provider limitation).
    Supports filtering by status, task IDs, model, and service tier.
    The server caps ``page_size`` at 100 to avoid oversized context.
    """
    await ctx.info("Listing Seedance tasks")
    await ctx.report_progress(progress=20, total=100)
    owner = get_principal(ctx)
    owned_task_ids = await get_runtime(ctx).ownership_store.list_task_ids(owner)

    requested_task_ids = input.task_ids
    if not owner.is_local:
        requested_task_ids = (
            sorted(owned_task_ids)
            if input.task_ids is None
            else sorted(set(input.task_ids) & owned_task_ids)
        )
        if not requested_task_ids:
            return SeedanceTaskPage(
                tasks=[],
                total=0,
                page=input.page or 1,
                page_size=input.page_size or 20,
                has_more=False,
            )

    service = SeedanceService()
    try:
        response, request_id = await call_with_retry(
            lambda: service.list_tasks(
                page=input.page or 1,
                page_size=input.page_size or 20,
                status=input.status,
                task_ids=requested_task_ids,
                model=input.model,
                service_tier=input.service_tier,
            )
        )
    except ProviderError as exc:
        await ctx.error(f"Failed to list tasks: {exc.message}")
        return provider_error_result(exc)
    finally:
        await service.close()

    await ctx.report_progress(progress=100, total=100)
    log_info(
        "seedance_tasks_listed",
        count=len(response.data),
        total=response.total,
        request_id=request_id,
    )

    return SeedanceTaskPage(
        tasks=[SeedanceService.to_task_summary(t) for t in response.data],
        total=response.total,
        page=input.page or 1,
        page_size=input.page_size or 20,
        has_more=response.has_more or False,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
