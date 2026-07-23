"""Compatibility guard for the removed process-global artifact registry.

Artifact persistence is owned by :class:`modelark_mcp.runtime.RuntimeServices`.
Keeping this importable for one release gives downstream callers an actionable
error instead of silently creating a second, unauthenticated store.
"""

from __future__ import annotations

from typing import Never


def get_artifact_store() -> Never:
    """Reject use of the removed global registry."""
    raise RuntimeError(
        "The global artifact registry was removed; obtain the store from "
        "RuntimeServices in the FastMCP lifespan context."
    )


def reset_artifact_store() -> None:
    """Deprecated no-op retained for import compatibility."""
