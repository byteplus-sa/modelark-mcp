"""LAS (Lake AI Service) HTTP gateway — client for ASR speech-to-text.

LAS uses ``Authorization: <key>`` (bare key, no ``Bearer`` prefix), distinct
from both ModelArk (``Bearer``) and Seed Speech (``X-Api-Key``). Unlike
ModelArk and Seed Speech, LAS returns the diagnostic ``request_id`` in the
response body (``metadata.request_id``) rather than in a response header.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error
from modelark_mcp.providers.base import BaseHttpGateway

if TYPE_CHECKING:
    import httpx


class LasGateway(BaseHttpGateway):
    """Authenticated HTTP client for BytePlus LAS (Lake AI Service)."""

    PROVIDER: ClassVar[ProviderName] = "las"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.las_api_key
        self._base_url = (base_url or settings.las_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def post(
        self,
        path: str,
        json_body: dict[str, Any],
    ) -> httpx.Response:
        """POST to LAS and return the raw response."""
        return await self._request("POST", path, json=json_body)

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        """Attempt to extract a diagnostic request ID from response headers.

        LAS primarily returns ``request_id`` in the response body
        (``metadata.request_id``), not in headers. This method is kept for
        ``BaseHttpGateway`` contract compliance and may return ``None``.
        """
        value = response.headers.get("X-Request-Id") or response.headers.get("x-request-id")
        return str(value) if value is not None else None

    @classmethod
    def normalize_error(cls, response: httpx.Response, operation: str) -> ProviderError:
        """Normalize an error HTTP response into a ``ProviderError``.

        LAS error bodies follow the same envelope as success responses:
        ``{"metadata": {"business_code": "...", "error_msg": "...", "request_id": "..."}}``.
        """
        status = response.status_code

        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"metadata": {"error_msg": response.text}}

        metadata = body.get("metadata", body) if isinstance(body, dict) else {}
        code = str(metadata.get("business_code", "")) if isinstance(metadata, dict) else ""
        message = metadata.get("error_msg", str(body)) if isinstance(metadata, dict) else str(body)
        request_id = metadata.get("request_id") if isinstance(metadata, dict) else None

        retryable = status == 429 or status >= 500
        mutation = operation in {"submit_asr_task"}
        retry_after = response.headers.get("Retry-After")
        try:
            retry_after_seconds = float(retry_after) if retry_after is not None else None
        except ValueError:
            retry_after_seconds = None

        normalized = NormalizedProviderError(
            provider=cls.PROVIDER,
            operation=operation,
            http_status=status,
            code=code or None,
            message=message,
            request_id=request_id,
            retryable=retryable,
            ambiguous_completion=mutation and status >= 500,
            retry_after_seconds=retry_after_seconds,
        )
        log_error(
            "las_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            request_id=request_id,
        )
        return ProviderError(normalized)
