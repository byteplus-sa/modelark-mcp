"""BytePlus VOD OpenAPI gateway with HMAC-SHA256 request signing.

Implements the BytePlus OpenAPI V4 signing scheme documented at
https://docs.byteplus.com/en/docs/byteplus-platform/reference-how-to-calculate-a-signature:

- Canonical request: ``METHOD\n/\nCanonicalQueryString\nCanonicalHeaders\nSignedHeaders\nHexEncode(Hash(Payload))``
- Credential scope: ``{YYYYMMDD}/{region}/vod/request``
- Authorization: ``HMAC-SHA256 Credential={AK}/{scope}, SignedHeaders={...}, Signature={hex}``

The VOD OpenAPI accepts query-string ``Action``/``Version`` parameters on path
``/``. This gateway never logs or returns the secret key or the signed
``Authorization`` header.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.providers.base import BaseHttpGateway
from modelark_mcp.providers.vod.schemas import VodResponseMetadata

_SIGNED_HEADERS_WITH_BODY = ("content-type", "host", "x-content-sha256", "x-date")
_SIGNED_HEADERS_NO_BODY = ("host", "x-content-sha256", "x-date")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hmac_hex(key: bytes, message: str) -> str:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _rfc3986_quote(value: str) -> str:
    return quote(value, safe="-_.~")


def build_canonical_query_string(query: dict[str, str]) -> str:
    """Sort and percent-encode query parameters into a canonical string."""
    return "&".join(
        f"{_rfc3986_quote(key)}={_rfc3986_quote(value)}" for key, value in sorted(query.items())
    )


class VodOpenApiGateway(BaseHttpGateway):
    """Signature-authenticated client for the BytePlus VOD OpenAPI."""

    PROVIDER: ClassVar[ProviderName] = "byteplus-vod"
    SERVICE: ClassVar[str] = "vod"
    VERSION: ClassVar[str] = "2025-07-01"

    def __init__(
        self,
        *,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._access_key_id = access_key_id or settings.vod_access_key_id
        self._secret_access_key = secret_access_key or settings.vod_secret_access_key
        self._region = region or settings.vod_region
        self._base_url = (base_url or settings.vod_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        value = response.headers.get("x-tt-logid")
        return str(value) if value is not None else None

    def _signing_key(self, short_date: str) -> bytes:
        key = self._secret_access_key.encode("utf-8")
        key = hmac.new(key, short_date.encode("utf-8"), hashlib.sha256).digest()
        key = hmac.new(key, self._region.encode("utf-8"), hashlib.sha256).digest()
        key = hmac.new(key, self.SERVICE.encode("utf-8"), hashlib.sha256).digest()
        return hmac.new(key, b"request", hashlib.sha256).digest()

    def _authorization_headers(
        self,
        method: str,
        query_string: str,
        payload: bytes,
        *,
        signed_header_names: tuple[str, ...],
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        request_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = now.strftime("%Y%m%d")

        content_sha256 = _sha256_hex(payload)
        host = httpx.URL(self._base_url).host or "vod.byteplusapi.com"

        header_values = {
            "content-type": "application/json; charset=utf-8",
            "host": host,
            "x-content-sha256": content_sha256,
            "x-date": request_date,
        }
        signed_headers = {name: header_values[name] for name in sorted(signed_header_names)}
        canonical_headers = "".join(f"{name}:{value}\n" for name, value in signed_headers.items())
        signed_headers_list = ";".join(signed_headers)

        canonical_request = "\n".join(
            (
                method,
                "/",
                query_string,
                canonical_headers,
                signed_headers_list,
                content_sha256,
            )
        )
        scope = f"{short_date}/{self._region}/{self.SERVICE}/request"
        string_to_sign = "\n".join(
            (
                "HMAC-SHA256",
                request_date,
                scope,
                _sha256_hex(canonical_request.encode("utf-8")),
            )
        )
        signature = _hmac_hex(self._signing_key(short_date), string_to_sign)

        return {
            "host": host,
            "x-date": request_date,
            "x-content-sha256": content_sha256,
            "authorization": (
                f"HMAC-SHA256 Credential={self._access_key_id}/{scope}, "
                f"SignedHeaders={signed_headers_list}, Signature={signature}"
            ),
        }

    async def post_json(self, query: dict[str, str], body: dict[str, Any]) -> httpx.Response:
        """POST a signed JSON body to the OpenAPI root path."""
        query_string = build_canonical_query_string(query)
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = self._authorization_headers(
            "POST",
            query_string,
            payload,
            signed_header_names=_SIGNED_HEADERS_WITH_BODY,
        )
        headers["content-type"] = "application/json; charset=utf-8"
        headers["accept"] = "application/json"
        return await self._request(
            "POST",
            f"/?{query_string}",
            headers=headers,
            content=payload,
        )

    async def get(self, query: dict[str, str]) -> httpx.Response:
        """GET a signed OpenAPI query."""
        query_string = build_canonical_query_string(query)
        payload = b""
        headers = self._authorization_headers(
            "GET",
            query_string,
            payload,
            signed_header_names=_SIGNED_HEADERS_NO_BODY,
        )
        headers["accept"] = "application/json"
        return await self._request(
            "GET",
            f"/?{query_string}",
            headers=headers,
        )

    @classmethod
    def normalize_error(cls, response: httpx.Response, operation: str) -> ProviderError:
        """Normalize VOD OpenAPI HTTP errors without exposing source URLs."""
        status = response.status_code
        request_id = cls.extract_request_id(response)
        code: str | None = None
        message: str | None = None
        try:
            parsed = response.json()
        except (json.JSONDecodeError, ValueError):
            parsed = None
        else:
            if isinstance(parsed, dict):
                metadata = VodResponseMetadata.model_validate(parsed.get("ResponseMetadata") or {})
                request_id = request_id or metadata.request_id
                if metadata.error:
                    code = metadata.error.effective_code
                    message = metadata.error.message

        fallback = f"VOD OpenAPI returned HTTP {status} during '{operation}'."
        safe_message = message or fallback
        ambiguous = status >= 500
        retryable = status == 429

        retry_after = response.headers.get("Retry-After")
        try:
            retry_after_seconds = float(retry_after) if retry_after is not None else None
        except ValueError:
            retry_after_seconds = None

        return ProviderError(
            NormalizedProviderError(
                provider=cls.PROVIDER,
                operation=operation,
                http_status=status,
                code=code or f"HTTP_{status}",
                message=safe_message,
                request_id=request_id,
                retryable=retryable,
                ambiguous_completion=ambiguous,
                retry_after_seconds=retry_after_seconds,
            )
        )

    @classmethod
    def normalize_ambiguous_transport_error(
        cls,
        operation: str,
        *,
        code: str,
        message: str,
    ) -> ProviderError:
        """Normalize a transport failure after mutation dispatch as ambiguous."""
        return ProviderError(
            NormalizedProviderError(
                provider=cls.PROVIDER,
                operation=operation,
                http_status=None,
                code=code,
                message=message,
                request_id=None,
                retryable=False,
                ambiguous_completion=True,
            )
        )
