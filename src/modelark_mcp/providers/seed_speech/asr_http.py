"""Seed Speech ASR HTTP gateway — submit + query for speech-to-text.

Seed Speech ASR uses ``X-Api-Key`` authentication (lowercase header),
distinct from ModelArk's ``Authorization: Bearer``. The gateway handles
submit (POST .../submit), query (POST .../query with incrementing
sequence), error normalization, and diagnostic ``X-Tt-Logid`` capture.

.. important::
   Query must use the **same** ``X-Api-Request-Id`` as submit, with
   **incrementing** ``X-Api-Sequence`` values (0, 1, 2, ...).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar, cast

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error
from modelark_mcp.providers.base import BaseHttpGateway

if TYPE_CHECKING:
    import httpx


class SeedSpeechAsrHttpGateway(BaseHttpGateway):
    """HTTP client for Seed Speech ASR submit + query."""

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
        self._api_key = api_key or settings.seed_speech_asr_api_key
        self._base_url = (base_url or settings.seed_speech_asr_base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_ms / 1000
        self._connect_timeout = connect_timeout or settings.connect_timeout_ms / 1000
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "X-Api-Resource-Id": "volc.seedasr.auc",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def submit(
        self,
        *,
        audio_data: str | None = None,
        audio_url: str | None = None,
        audio_format: str = "wav",
        language: str = "en-US",
        enable_punc: bool | None = None,
        enable_itn: bool | None = None,
        request_id: str,
    ) -> str:
        """Submit audio for ASR. Returns the task ID (request ID)."""
        audio: dict[str, Any] = {
            "format": audio_format,
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": language,
        }
        if audio_data is not None:
            audio["data"] = audio_data
        if audio_url is not None:
            audio["url"] = audio_url

        body: dict[str, Any] = {
            "user": {"uid": "modelark-mcp"},
            "audio": audio,
            "request": {
                "model_name": "bigmodel",
                "enable_itn": enable_itn is not False,
                "enable_punc": enable_punc is not False,
                "show_utterances": True,
                "vad_segment": False,
                "sensitive_words_filter": "",
            },
        }

        response = await self._request(
            "POST",
            "/api/v3/auc/bigmodel/submit",
            json=body,
            headers={
                **self._headers(),
                "X-Api-Request-Id": request_id,
                "X-Api-Sequence": "-1",
            },
        )
        if response.status_code >= 400:
            raise self.normalize_error(response, "submit")
        return request_id

    _NON_TERMINAL_STATUSES = frozenset({"20000001", "45000000"})

    async def query(self, *, task_id: str, sequence: int) -> dict[str, Any] | None:
        """Poll for ASR result. Returns None if still processing."""
        response = await self._request(
            "POST",
            "/api/v3/auc/bigmodel/query",
            json={"id": task_id},
            headers={
                **self._headers(),
                "X-Api-Request-Id": task_id,
                "X-Api-Sequence": str(sequence),
            },
        )
        if response.status_code >= 400:
            raise self.normalize_error(response, "query")
        api_status = response.headers.get("x-api-status-code", "")
        if api_status in self._NON_TERMINAL_STATUSES:
            return None
        return cast("dict[str, Any]", response.json())

    @staticmethod
    def extract_request_id(response: httpx.Response) -> str | None:
        value = response.headers.get("X-Tt-Logid") or response.headers.get("x-tt-logid")
        return str(value) if value is not None else None

    @staticmethod
    def extract_log_id_from_body(body: dict[str, Any]) -> str | None:
        """Extract log ID from query response body if present."""
        return None

    @classmethod
    def normalize_error(cls, response: httpx.Response, operation: str) -> ProviderError:
        log_id = cls.extract_request_id(response)
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
            "seed_speech_asr_error",
            operation=operation,
            http_status=status,
            code=normalized.code,
            retryable=retryable,
            log_id=log_id,
        )
        return ProviderError(normalized)
