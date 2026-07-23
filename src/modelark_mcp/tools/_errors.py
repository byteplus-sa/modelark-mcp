"""Shared error-result helpers for tool handlers."""

from __future__ import annotations

from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import ProviderError


def provider_error_result(exc: ProviderError) -> ToolResult:
    """Return a safe MCP error result with machine-readable normalized data."""
    payload = exc.error.model_dump(mode="json")
    return ToolResult(
        content=(f"{payload['provider']} {payload['operation']} failed: {payload['message']}"),
        structured_content={"error": payload},
        is_error=True,
    )
