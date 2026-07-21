"""ModelArk HTTP gateway — shared client for Seedream (image) and Seedance (video).

Both products use the ModelArk data-plane host with ``Authorization: Bearer``
authentication. The gateway handles request/response, error normalization, and
request ID capture.
"""

from __future__ import annotations

from typing import Any

import httpx

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error
from modelark_mcp.observability.logger import info as log_info


class ModelArkGateway:
    """Authenticated HTTP client for ModelArk API calls."""

    PROVIDER: ProviderName = "modelark"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.modelark_api_key
        self._base_url = (base_url or settings.modelark_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout),
                follow_redirects=False,
            )
        return self._client

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def post(self, path: str, json_body: dict[str, Any]) -> httpx.Response:
        """POST to ModelArk and return the raw response."""
        client = await self._ensure_client()
        url = f"{self._base_url}{path}"
        log_info("modelark_request", method="POST", path=path)
        return await client.post(url, json=json_body, headers=self._headers())

    async def get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET from ModelArk and return the raw response."""
        client = await self._ensure_client()
        url = f"{self._base_url}{path}"
        log_info("modelark_request", method="GET", path=path)
        return await client.get(url, params=params, headers=self._headers())

    async def delete(self, path: str) -> httpx.Response:
        """DELETE on ModelArk and return the raw response."""
        client = await self._ensure_client()
        url = f"{self._base_url}{path}"
        log_info("modelark_request", method="DELETE", path=path)
        return await client.delete(url, headers=self._headers())

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        """Extract the ModelArk request ID from response headers."""
        value = response.headers.get("X-Request-Id") or response.headers.get("x-request-id")
        return str(value) if value is not None else None

    @staticmethod
    def normalize_error(
        response: httpx.Response,
        operation: str,
    ) -> ProviderError:
        """Normalize an error HTTP response into a ``ProviderError``."""
        request_id = ModelArkGateway.extract_request_id(response)
        status = response.status_code

        try:
            body = response.json()
        except Exception:
            body = {"error": {"message": response.text}}

        error_obj = body.get("error", body) if isinstance(body, dict) else {}
        code = str(error_obj.get("code", "")) if isinstance(error_obj, dict) else ""
        message = error_obj.get("message", str(body)) if isinstance(error_obj, dict) else str(body)

        # Retryable: 429 (rate limit) and 5xx (server errors).
        retryable = status == 429 or status >= 500

        normalized = NormalizedProviderError(
            provider="modelark",
            operation=operation,
            http_status=status,
            code=code or None,
            message=message,
            request_id=request_id,
            retryable=retryable,
        )
        log_error(
            "modelark_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            request_id=request_id,
        )
        return ProviderError(normalized)

    @staticmethod
    def normalize_timeout(operation: str) -> ProviderError:
        """Normalize a timeout into a ``ProviderError``.

        A mutation timeout has ambiguous completion — the billable operation
        may have succeeded upstream.
        """
        return ProviderError(
            NormalizedProviderError(
                provider="modelark",
                operation=operation,
                http_status=None,
                code="TIMEOUT",
                message=(
                    f"Request timed out during '{operation}'. "
                    "The upstream operation may have succeeded. "
                    "Do not retry blindly; reconcile using the task ID or request ID."
                ),
                request_id=None,
                retryable=False,
                ambiguous_completion=True,
            )
        )

    @staticmethod
    def normalize_connection_error(operation: str, exc: Exception) -> ProviderError:
        """Normalize a connection error."""
        return ProviderError(
            NormalizedProviderError(
                provider="modelark",
                operation=operation,
                http_status=None,
                code="CONNECTION_ERROR",
                message=f"Failed to connect to ModelArk: {exc}",
                request_id=None,
                retryable=True,
            )
        )
