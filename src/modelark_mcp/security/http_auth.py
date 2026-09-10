"""FastMCP HTTP authentication and component-scope policy."""

from __future__ import annotations

import time
from typing import Any

from fastmcp.server.auth import (
    AccessToken,
    AuthCheck,
    AuthProvider,
    JWTVerifier,
    RemoteAuthProvider,
    require_scopes,
)
from pydantic import AnyHttpUrl

from modelark_mcp.config.env import AuthMode, Settings
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.observability.logger import warning as log_warning


class StrictJWTVerifier(JWTVerifier):
    """JWT verifier pinned to RS256 that rejects tokens without an ``exp`` claim.

    Also enforces ``nbf`` (not-valid-before) with a bounded clock-skew
    allowance, per RFC 8725 §3.10.
    """

    def __init__(self, *, clock_skew_seconds: int = 30, **kwargs: Any) -> None:
        kwargs.pop("algorithm", None)
        self._clock_skew_seconds = clock_skew_seconds
        super().__init__(algorithm="RS256", **kwargs)

    async def verify_token(self, token: str) -> AccessToken | None:
        verified = await super().verify_token(token)
        if verified is None:
            log_warning("jwt_verification_failed", reason="invalid_token")
            return None
        claims = verified.claims or {}
        if claims.get("exp") is None:
            log_warning("jwt_verification_failed", reason="missing_exp")
            return None
        nbf = claims.get("nbf")
        if isinstance(nbf, (int, float)) and nbf > time.time() + self._clock_skew_seconds:
            log_warning("jwt_verification_failed", reason="token_not_yet_valid")
            return None
        log_info("jwt_verified", subject=verified.subject, client_id=verified.client_id)
        return verified


def build_auth_provider(settings: Settings) -> AuthProvider | None:
    """Build the configured verifier; local stdio/loopback mode uses none.

    In JWT mode this returns either a bare :class:`StrictJWTVerifier` (internal
    machine-to-machine validation, no OAuth discovery) or, when
    ``MCP_JWT_PROVIDE_DISCOVERY`` is enabled, a :class:`RemoteAuthProvider`
    that additionally serves RFC 9728 Protected Resource Metadata so
    spec-compliant MCP clients can discover the authorization server.
    """
    if settings.mcp_auth_mode is AuthMode.LOCAL:
        log_info("auth_mode", mode="local")
        return None
    log_info(
        "auth_mode",
        mode="jwt",
        provide_discovery=settings.mcp_jwt_provide_discovery,
    )
    verifier = StrictJWTVerifier(
        jwks_uri=settings.mcp_jwt_jwks_uri,
        issuer=settings.mcp_jwt_issuer,
        audience=settings.mcp_jwt_audience,
        ssrf_safe=True,
        clock_skew_seconds=settings.mcp_jwt_clock_skew_seconds,
    )
    if not settings.mcp_jwt_provide_discovery:
        return verifier
    scopes_supported = settings.jwt_scopes_supported or None
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AnyHttpUrl(url=settings.mcp_jwt_issuer or "")],
        base_url=settings.mcp_public_base_url,
        scopes_supported=scopes_supported,
    )


def component_auth(settings: Settings, *scopes: str) -> AuthCheck | None:
    """Require scopes only when token authentication is active."""
    if settings.mcp_auth_mode is AuthMode.LOCAL:
        return None
    return require_scopes(*scopes)
