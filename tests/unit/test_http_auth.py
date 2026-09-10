"""Unit tests for the strict JWT verifier (RS256 pinned, ``exp`` required)."""

from __future__ import annotations

import time

import pytest
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk
from joserfc import jwt as joserfc_jwt

from modelark_mcp.config.env import Settings
from modelark_mcp.security.http_auth import StrictJWTVerifier, build_auth_provider

ISSUER = "https://identity.example.com"
AUDIENCE = "modelark-mcp"


@pytest.fixture
def key_pair() -> RSAKeyPair:
    return RSAKeyPair.generate()


def _verifier(key_pair: RSAKeyPair) -> StrictJWTVerifier:
    return StrictJWTVerifier(
        public_key=key_pair.public_key,
        issuer=ISSUER,
        audience=AUDIENCE,
    )


def _encode_without_exp(key_pair: RSAKeyPair, *, subject: str) -> str:
    signing_key = jwk.import_key(key_pair.private_key.get_secret_value(), "RSA")
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "sub": subject,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(time.time()),
    }
    return joserfc_jwt.encode(header, claims, signing_key, algorithms=["RS256"])


def _encode_with_nbf(key_pair: RSAKeyPair, *, nbf: int) -> str:
    signing_key = jwk.import_key(key_pair.private_key.get_secret_value(), "RSA")
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "sub": "alice",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "nbf": nbf,
    }
    return joserfc_jwt.encode(header, claims, signing_key, algorithms=["RS256"])


class TestStrictJWTVerifier:
    async def test_accepts_valid_token_with_exp(self, key_pair: RSAKeyPair) -> None:
        token = key_pair.create_token(
            subject="alice",
            issuer=ISSUER,
            audience=AUDIENCE,
            expires_in_seconds=3600,
        )
        verified = await _verifier(key_pair).verify_token(token)
        assert verified is not None
        assert (verified.claims or {}).get("sub") == "alice"

    async def test_rejects_expired_token(self, key_pair: RSAKeyPair) -> None:
        token = key_pair.create_token(
            subject="alice",
            issuer=ISSUER,
            audience=AUDIENCE,
            expires_in_seconds=-60,
        )
        assert await _verifier(key_pair).verify_token(token) is None

    async def test_rejects_token_without_exp(self, key_pair: RSAKeyPair) -> None:
        token = _encode_without_exp(key_pair, subject="alice")
        assert await _verifier(key_pair).verify_token(token) is None

    async def test_rejects_token_not_yet_valid(self, key_pair: RSAKeyPair) -> None:
        token = _encode_with_nbf(key_pair, nbf=int(time.time()) + 3600)
        assert await _verifier(key_pair).verify_token(token) is None

    async def test_accepts_token_with_past_nbf(self, key_pair: RSAKeyPair) -> None:
        token = _encode_with_nbf(key_pair, nbf=int(time.time()) - 60)
        assert await _verifier(key_pair).verify_token(token) is not None


class TestBuildAuthProvider:
    def test_local_mode_returns_none(self) -> None:
        settings = Settings(_env_file=None, MCP_AUTH_MODE="local")
        assert build_auth_provider(settings) is None

    def test_jwt_mode_returns_strict_verifier(self) -> None:
        settings = Settings(
            _env_file=None,
            MCP_AUTH_MODE="jwt",
            MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
            MCP_JWT_ISSUER="https://identity.example.com",
            MCP_JWT_AUDIENCE="modelark-mcp",
        )
        provider = build_auth_provider(settings)
        assert isinstance(provider, StrictJWTVerifier)

    def test_discovery_mode_returns_remote_provider(self) -> None:
        from fastmcp.server.auth import RemoteAuthProvider

        settings = Settings(
            _env_file=None,
            MCP_AUTH_MODE="jwt",
            MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
            MCP_JWT_ISSUER="https://identity.example.com",
            MCP_JWT_AUDIENCE="modelark-mcp",
            MCP_JWT_PROVIDE_DISCOVERY=True,
            MCP_PUBLIC_BASE_URL="https://mcp.example.com",
            MCP_JWT_SCOPES_SUPPORTED="seedream:generate,vod:enhance",
        )
        provider = build_auth_provider(settings)
        assert isinstance(provider, RemoteAuthProvider)

    def test_discovery_requires_public_base_url(self) -> None:
        with pytest.raises(ValueError, match="MCP_PUBLIC_BASE_URL"):
            Settings(
                _env_file=None,
                MCP_AUTH_MODE="jwt",
                MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
                MCP_JWT_ISSUER="https://identity.example.com",
                MCP_JWT_AUDIENCE="modelark-mcp",
                MCP_JWT_PROVIDE_DISCOVERY=True,
            )

    def test_discovery_requires_http_url_issuer(self) -> None:
        with pytest.raises(ValueError, match="MCP_JWT_ISSUER"):
            Settings(
                _env_file=None,
                MCP_AUTH_MODE="jwt",
                MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
                MCP_JWT_ISSUER="urn:example:issuer",
                MCP_JWT_AUDIENCE="modelark-mcp",
                MCP_JWT_PROVIDE_DISCOVERY=True,
                MCP_PUBLIC_BASE_URL="https://mcp.example.com",
            )

    def test_bare_jwt_mode_accepts_non_url_issuer(self) -> None:
        settings = Settings(
            _env_file=None,
            MCP_AUTH_MODE="jwt",
            MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
            MCP_JWT_ISSUER="urn:example:issuer",
            MCP_JWT_AUDIENCE="modelark-mcp",
        )
        provider = build_auth_provider(settings)
        assert isinstance(provider, StrictJWTVerifier)
