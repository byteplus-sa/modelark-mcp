"""Bearer-authenticated HTTP gateway for BytePlus VOD AI MediaKit."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error
from modelark_mcp.providers.base import BaseHttpGateway
from modelark_mcp.providers.vod_mediakit.schemas import VodMediaKitProviderErrorResponse

if TYPE_CHECKING:
    import httpx

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def sanitize_provider_message(message: str, fallback: str) -> str:
    """Remove URLs from provider text before returning it to clients."""
    cleaned = _URL_PATTERN.sub("[REDACTED_URL]", message).strip()
    return cleaned or fallback


class VodMediaKitGateway(BaseHttpGateway):
    """Authenticated client exposing only the verified enhancement POST."""

    PROVIDER: ClassVar[ProviderName] = "byteplus-vod-mediakit"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.vod_mediakit_api_key
        self._base_url = (base_url or settings.vod_mediakit_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def post(self, path: str, json_body: dict[str, Any]) -> httpx.Response:
        """POST to the verified MediaKit endpoint and return the raw response."""
        return await self._request("POST", path, json=json_body)

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        """Extract the MediaKit diagnostic ``x-tt-logid`` header."""
        value = response.headers.get("x-tt-logid")
        return str(value) if value is not None else None

    @classmethod
    def normalize_error(cls, response: httpx.Response, operation: str) -> ProviderError:
        """Normalize MediaKit HTTP errors without exposing source URLs."""
        status = response.status_code
        request_id = cls.extract_request_id(response)
        try:
            parsed = VodMediaKitProviderErrorResponse.model_validate(response.json())
        except (json.JSONDecodeError, ValueError):
            parsed = VodMediaKitProviderErrorResponse()

        detail = parsed.error
        fallback = f"MediaKit returned HTTP {status} during '{operation}'."
        message = sanitize_provider_message(detail.message or "", fallback) if detail else fallback
        code = detail.code if detail else None
        if not code and detail and detail.type:
            code = detail.type

        retry_after = response.headers.get("Retry-After")
        try:
            retry_after_seconds = float(retry_after) if retry_after is not None else None
        except ValueError:
            retry_after_seconds = None

        ambiguous = status >= 500
        retryable = status == 429
        normalized = NormalizedProviderError(
            provider=cls.PROVIDER,
            operation=operation,
            http_status=status,
            code=code or f"HTTP_{status}",
            message=message,
            request_id=request_id,
            retryable=retryable,
            ambiguous_completion=ambiguous,
            retry_after_seconds=retry_after_seconds,
        )
        log_error(
            "vod_mediakit_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            ambiguous_completion=ambiguous,
            request_id=request_id,
        )
        return ProviderError(normalized)

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
