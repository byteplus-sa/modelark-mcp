"""FastMCP HTTP authentication and component-scope policy."""

from __future__ import annotations

from fastmcp.server.auth import AuthCheck, AuthProvider, JWTVerifier, require_scopes

from modelark_mcp.config.env import AuthMode, Settings


def build_auth_provider(settings: Settings) -> AuthProvider | None:
    """Build the configured verifier; local stdio/loopback mode uses none."""
    if settings.mcp_auth_mode is AuthMode.LOCAL:
        return None
    return JWTVerifier(
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
