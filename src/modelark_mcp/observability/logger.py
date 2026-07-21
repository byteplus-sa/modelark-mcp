"""Structured stderr logger for the ModelArk Seed MCP server.

Only MCP JSON-RPC messages go to stdout. All structured logs go to stderr,
as required by the ``stdio`` transport specification.

Never log: prompt text, full media URLs, Base64, subtitles, or credentials.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-api-key",
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "data",  # base64 media
        "audio",  # base64 media
        "image",  # base64 media
        "video",
    }
)


def _redact(value: Any) -> Any:
    """Recursively redact sensitive keys from a dict/list structure."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k.lower() in _REDACT_KEYS else _redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _emit(level: str, message: str, **fields: Any) -> None:
    """Emit a structured JSON log line to stderr."""
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level,
        "msg": message,
    }
    record.update(_redact(fields))
    # stderr only — stdout is reserved for MCP JSON-RPC.
    sys.stderr.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def debug(message: str, **fields: Any) -> None:
    _emit("DEBUG", message, **fields)


def info(message: str, **fields: Any) -> None:
    _emit("INFO", message, **fields)


def warning(message: str, **fields: Any) -> None:
    _emit("WARNING", message, **fields)


def error(message: str, **fields: Any) -> None:
    _emit("ERROR", message, **fields)
