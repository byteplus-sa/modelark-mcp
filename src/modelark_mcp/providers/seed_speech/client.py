"""Seed Speech HTTP gateway — client for Seed Audio (full-scene audio generation).

Seed Audio is hosted by Seed Speech and uses ``X-Api-Key`` authentication,
distinct from ModelArk's ``Authorization: Bearer``. The gateway handles
request/response, error normalization, and diagnostic ``X-Tt-Logid`` capture.
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


class SeedSpeechGateway(BaseHttpGateway):
    """Authenticated HTTP client for Seed Speech API calls."""

    PROVIDER: ClassVar[ProviderName] = "seed-speech"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.seed_audio_api_key
        self._base_url = (base_url or settings.seed_audio_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def post(
        self,
        path: str,
        json_body: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> httpx.Response:
        """POST to Seed Speech and return the raw response."""
        headers = self._headers()
        if request_id:
            headers["X-Api-Request-Id"] = request_id
        return await self._request("POST", path, json=json_body, headers=headers)

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        """Extract the diagnostic ``X-Tt-Logid`` from response headers."""
        value = response.headers.get("X-Tt-Logid") or response.headers.get("x-tt-logid")
        return str(value) if value is not None else None

    extract_log_id = extract_request_id

    @classmethod
    def normalize_error(cls, response: httpx.Response, operation: str) -> ProviderError:
        """Normalize an error HTTP response into a ``ProviderError``."""
        log_id = cls.extract_log_id(response)
        status = response.status_code

        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"message": response.text}

        code = str(body.get("code", "")) if isinstance(body, dict) else ""
        message = body.get("message", str(body)) if isinstance(body, dict) else str(body)

        retryable = status == 429 or status >= 500
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
            request_id=log_id,
            retryable=retryable,
            ambiguous_completion=status >= 500,
            retry_after_seconds=retry_after_seconds,
        )
        log_error(
            "seed_speech_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            log_id=log_id,
        )
        return ProviderError(normalized)
