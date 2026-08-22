"""FastMCP HTTP authentication and component-scope policy."""

from __future__ import annotations

from typing import Any

from fastmcp.server.auth import (
    AccessToken,
    AuthCheck,
    AuthProvider,
    JWTVerifier,
    require_scopes,
)

from modelark_mcp.config.env import AuthMode, Settings


class StrictJWTVerifier(JWTVerifier):
    """JWT verifier pinned to RS256 that rejects tokens without an ``exp`` claim."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("algorithm", None)
        super().__init__(algorithm="RS256", **kwargs)

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await super().verify_token(token)
        if verified is None or (verified.claims or {}).get("exp") is None:
            return None
        return verified


def build_auth_provider(settings: Settings) -> AuthProvider | None:
    """Build the configured verifier; local stdio/loopback mode uses none."""
    if settings.mcp_auth_mode is AuthMode.LOCAL:
        return None
    return StrictJWTVerifier(
        jwks_uri=settings.mcp_jwt_jwks_uri,
        issuer=settings.mcp_jwt_issuer,
        audience=settings.mcp_jwt_audience,
        ssrf_safe=True,
    )


def component_auth(settings: Settings, *scopes: str) -> AuthCheck | None:
    """Require scopes only when token authentication is active."""
    if settings.mcp_auth_mode is AuthMode.LOCAL:
        return None
    return require_scopes(*scopes)
