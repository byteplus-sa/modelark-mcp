"""Low-cardinality Prometheus metrics and FastMCP request instrumentation."""

from __future__ import annotations

import asyncio
import inspect
from functools import wraps
from time import perf_counter
from typing import TYPE_CHECKING, cast

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp_tasks.context import get_task_context
from fastmcp_tasks.models import CreateTaskResult
from prometheus_client import Counter, Histogram

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import mcp.types as mt
    from fastmcp.tools import ToolResult

TOOL_REQUESTS = Counter(
    "modelark_mcp_tool_requests_total",
    "MCP tool requests by tool and outcome.",
    ("tool", "status"),
)
TOOL_DURATION = Histogram(
    "modelark_mcp_tool_duration_seconds",
    "MCP tool execution duration.",
    ("tool",),
)
TOOL_ADMISSION_DURATION = Histogram(
    "modelark_mcp_tool_admission_duration_seconds",
    "MCP background task admission duration, excluding worker execution.",
    ("tool",),
)
PROVIDER_REQUESTS = Counter(
    "modelark_mcp_provider_requests_total",
    "Provider requests by provider, operation, and outcome.",
    ("provider", "operation", "status"),
)
PROVIDER_DURATION = Histogram(
    "modelark_mcp_provider_duration_seconds",
    "Provider request duration.",
    ("provider", "operation"),
)
ARTIFACT_OPERATIONS = Counter(
    "modelark_mcp_artifact_operations_total",
    "Artifact operations by operation, outcome, and media type.",
    ("operation", "status", "media_type"),
)
BUDGET_REJECTIONS = Counter(
    "modelark_mcp_budget_rejections_total",
    "Budget rejections by product.",
    ("product",),
)
RETRY_ATTEMPTS = Counter(
    "modelark_mcp_retry_attempts_total",
    "Safe provider retry attempts.",
    ("provider", "operation"),
)


def instrument_tool_execution[**Parameters, ReturnValue](
    handler: Callable[Parameters, Awaitable[ReturnValue]], *, tool_name: str
) -> Callable[Parameters, Awaitable[ReturnValue]]:
    """Measure real task workers while preserving foreground middleware counts."""

    @wraps(handler)
    async def measured(*args: Parameters.args, **kwargs: Parameters.kwargs) -> ReturnValue:
        if get_task_context() is None:
            return await handler(*args, **kwargs)
        started = perf_counter()
        try:
            result = await handler(*args, **kwargs)
        except asyncio.CancelledError:
            TOOL_REQUESTS.labels(tool=tool_name, status="cancelled").inc()
            raise
        except Exception:
            TOOL_REQUESTS.labels(tool=tool_name, status="exception").inc()
            raise
        else:
            status = "error" if getattr(result, "is_error", False) else "success"
            TOOL_REQUESTS.labels(tool=tool_name, status=status).inc()
            return result
        finally:
            TOOL_DURATION.labels(tool=tool_name).observe(perf_counter() - started)

    measured.__dict__["__signature__"] = inspect.signature(handler, eval_str=True)
    return measured


class MetricsMiddleware(Middleware):
    """Measure MCP tool calls without tenant, model, URL, or request labels."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name = context.message.name
        started = perf_counter()
        accepted = False
        try:
            result = cast("ToolResult | CreateTaskResult", await call_next(context))
        except asyncio.CancelledError:
            TOOL_REQUESTS.labels(tool=tool_name, status="cancelled").inc()
            raise
        except Exception:
            TOOL_REQUESTS.labels(tool=tool_name, status="exception").inc()
            raise
        else:
            if isinstance(result, CreateTaskResult):
                accepted = True
                status = "accepted"
            else:
                status = "error" if result.is_error else "success"
            TOOL_REQUESTS.labels(tool=tool_name, status=status).inc()
            return cast("ToolResult", result)
        finally:
            duration = TOOL_ADMISSION_DURATION if accepted else TOOL_DURATION
            duration.labels(tool=tool_name).observe(perf_counter() - started)
