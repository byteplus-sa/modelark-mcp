"""Test utilities for the ModelArk Seed MCP server.

Provides a ``FakeContext`` that implements the minimal ``Context`` interface
needed by tool handlers, without requiring a live MCP connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeContext:
    """Minimal Context implementation for testing tool handlers."""

    messages: list[str] = field(default_factory=list)
    progress_reports: list[tuple[int, int]] = field(default_factory=list)
    lifespan_context: dict[str, Any] = field(default_factory=dict)

    async def info(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"INFO: {message}")

    async def debug(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"DEBUG: {message}")

    async def warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"WARNING: {message}")

    async def error(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"ERROR: {message}")

    async def report_progress(self, progress: int, total: int) -> None:
        self.progress_reports.append((progress, total))

    async def read_resource(self, uri: str) -> object:
        raise NotImplementedError

    async def sample(self, messages: object, **kwargs: object) -> object:
        raise NotImplementedError
