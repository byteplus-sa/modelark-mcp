"""Shared task-response normalization for VOD AI MediaKit adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from modelark_mcp.providers.vod_mediakit.client import sanitize_provider_message


def normalize_timestamp(value: str | int | None) -> str | None:
    """Normalize a provider Unix-seconds or ISO-8601 timestamp to ISO-8601 UTC."""
    if value is None:
        return None
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if value.strip().isdigit():
        return normalize_timestamp(int(value.strip()))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def sanitize_task_error(detail: Any, fallback: str) -> tuple[str | None, str]:
    """Extract a safe failure code and message from a task error detail."""
    if detail is None:
        return None, fallback
    code = getattr(detail, "code", None)
    message = getattr(detail, "message", None)
    return (
        code if isinstance(code, str) and code else None,
        sanitize_provider_message(message or "", fallback),
    )
