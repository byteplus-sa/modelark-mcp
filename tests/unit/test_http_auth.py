"""Unit tests for the strict JWT verifier (RS256 pinned, ``exp`` required)."""

from __future__ import annotations

import time

import pytest
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk
from joserfc import jwt as joserfc_jwt

from modelark_mcp.security.http_auth import StrictJWTVerifier

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
