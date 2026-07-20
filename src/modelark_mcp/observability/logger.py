"""Structured stderr logger for the ModelArk Seed MCP server.

Built on ``structlog`` with a JSON renderer writing to stderr.
Only MCP JSON-RPC messages go to stdout. All structured logs go to stderr,
as required by the ``stdio`` transport specification.

Never log: prompt text, full media URLs, Base64, subtitles, or credentials.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-api-key",
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "data",
        "audio",
        "image",
        "video",
    }
)


def _redact(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive keys from the event dict."""

    def _redact_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ("[REDACTED]" if k.lower() in _REDACT_KEYS else _redact_value(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_redact_value(item) for item in value]
        return value

    return {k: _redact_value(v) for k, v in event_dict.items()}


_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter("%(message)s"))

_root_logger = logging.getLogger()
_root_logger.handlers.clear()
_root_logger.addHandler(_stderr_handler)
_root_logger.setLevel(logging.DEBUG)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.dev.set_exc_info,
        _redact,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

_logger = structlog.get_logger("modelark-mcp")


def debug(message: str, **fields: Any) -> None:
    _logger.debug(message, **fields)


def info(message: str, **fields: Any) -> None:
    _logger.info(message, **fields)


def warning(message: str, **fields: Any) -> None:
    _logger.warning(message, **fields)


def error(message: str, **fields: Any) -> None:
    _logger.error(message, **fields)
