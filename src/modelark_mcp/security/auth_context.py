"""Auth context for multi-tenant artifact and task ownership.

In ``stdio`` mode, there is a single principal (the local user). In remote
HTTP mode, the auth context is derived from the MCP request context (OAuth
scopes, principal ID). This module provides the abstraction for both.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    """Principal identity and tenant for ownership checks."""

    principal_id: str = "local"
    tenant_id: str = "local"

    @property
    def is_local(self) -> bool:
        return self.principal_id == "local"
