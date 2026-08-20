"""Contract tests for the BytePlus VOD OpenAPI HMAC-SHA256 signing gateway.

Pins the canonical-request, string-to-sign, signing-key, and Authorization
header construction against independently computed expected values so any
drift in the signing algorithm is caught offline.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

import pytest

from modelark_mcp.providers.vod import client as client_module
from modelark_mcp.providers.vod.client import (
    VodOpenApiGateway,
    build_canonical_query_string,
)

AK = "AKLTtest"
SK = "sk-test-secret"
REGION = "ap-southeast-1"
BASE_URL = "https://vod.byteplusapi.com"
HOST = "vod.byteplusapi.com"
FIXED_NOW = datetime(2026, 8, 19, 8, 15, 30, tzinfo=UTC)
REQUEST_DATE = "20260819T081530Z"
SHORT_DATE = "20260819"


class _FixedDatetime:
    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return FIXED_NOW


@pytest.fixture
def gateway() -> VodOpenApiGateway:
    return VodOpenApiGateway(
        access_key_id=AK,  # pragma: allowlist secret
        secret_access_key=SK,  # pragma: allowlist secret
        region=REGION,
        base_url=BASE_URL,
        timeout=10.0,
        connect_timeout=5.0,
    )


def _signing_key(sk: str, short_date: str, region: str, service: str) -> bytes:
    key = sk.encode("utf-8")
    key = hmac.new(key, short_date.encode("utf-8"), hashlib.sha256).digest()
    key = hmac.new(key, region.encode("utf-8"), hashlib.sha256).digest()
    key = hmac.new(key, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key, b"request", hashlib.sha256).digest()


def _expected_authorization(canonical_request: str, signed_headers: str) -> str:
    scope = f"{SHORT_DATE}/{REGION}/vod/request"
    string_to_sign = "\n".join(
        (
            "HMAC-SHA256",
            REQUEST_DATE,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        )
    )
    signature = hmac.new(
        _signing_key(SK, SHORT_DATE, REGION, "vod"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"HMAC-SHA256 Credential={AK}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def test_canonical_query_string_sorts_and_encodes() -> None:
    result = build_canonical_query_string(
        {"Version": "2025-07-01", "Action": "StartExecution", "RunId": "r 1&2"}
    )
    assert result == "Action=StartExecution&RunId=r%201%262&Version=2025-07-01"


def test_post_authorization_matches_expected_signature(
    gateway: VodOpenApiGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_module, "datetime", _FixedDatetime)
    payload = b'{"Input":{"Type":"DirectUrl","DirectUrl":{"FileName":"a.mp4"}}}'
    query_string = "Action=StartExecution&Version=2025-07-01"
    content_sha256 = hashlib.sha256(payload).hexdigest()

    canonical_headers = (
        f"content-type:application/json; charset=utf-8\n"
        f"host:{HOST}\n"
        f"x-content-sha256:{content_sha256}\n"
        f"x-date:{REQUEST_DATE}\n"
    )
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_request = "\n".join(
        (
            "POST",
            "/",
            query_string,
            canonical_headers,
            signed_headers,
            content_sha256,
        )
    )

    headers = gateway._authorization_headers(
        "POST",
        query_string,
        payload,
        signed_header_names=("content-type", "host", "x-content-sha256", "x-date"),
    )

    assert headers["x-date"] == REQUEST_DATE
    assert headers["x-content-sha256"] == content_sha256
    assert headers["host"] == HOST
    assert headers["authorization"] == _expected_authorization(canonical_request, signed_headers)


def test_get_authorization_uses_empty_payload_hash(
    gateway: VodOpenApiGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_module, "datetime", _FixedDatetime)
    payload = b""
    query_string = "Action=GetExecution&RunId=r1&Version=2025-07-01"
    content_sha256 = hashlib.sha256(payload).hexdigest()

    canonical_headers = f"host:{HOST}\nx-content-sha256:{content_sha256}\nx-date:{REQUEST_DATE}\n"
    signed_headers = "host;x-content-sha256;x-date"
    canonical_request = "\n".join(
        (
            "GET",
            "/",
            query_string,
            canonical_headers,
            signed_headers,
            content_sha256,
        )
    )

    headers = gateway._authorization_headers(
        "GET",
        query_string,
        payload,
        signed_header_names=("host", "x-content-sha256", "x-date"),
    )

    assert "content-type" not in headers
    assert headers["authorization"] == _expected_authorization(canonical_request, signed_headers)
