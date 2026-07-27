"""Seed Speech ASR adapter — speech-to-text over HTTP submit + query.

Submits audio (base64-encoded bytes or public URL) to Seed Speech ASR,
then polls until the transcription is ready. All polling is hidden from
the caller — one call, one complete result.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any
from uuid import uuid4

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.domain.transcription import (
    TranscriptionResult,
    TranscriptionUtterance,
    TranscriptionWord,
)
from modelark_mcp.providers.seed_speech.asr_http import SeedSpeechAsrHttpGateway


class SeedSpeechAsrService:
    """Service layer for Seed Speech ASR (speech-to-text)."""

    def __init__(
        self,
        gateway: SeedSpeechAsrHttpGateway | None = None,
    ) -> None:
        self._gateway = gateway

    async def transcribe(
        self,
        *,
        audio_bytes: bytes | None = None,
        audio_url: str | None = None,
        audio_format: str = "wav",
        language: str = "en-US",
        enable_punc: bool | None = None,
        enable_itn: bool | None = None,
        poll_interval: float = 3.0,
        poll_max: float = 600.0,
    ) -> tuple[TranscriptionResult, str | None]:
        """Transcribe audio via HTTP submit + query.

        Returns ``(result, log_id)``. Blocks until the transcription is ready
        or ``poll_max`` seconds elapse.

        Args:
            audio_bytes: Raw audio bytes (base64-encoded for submit).
            audio_url: Public URL of the audio file (passed directly).
            audio_format: Audio format string (e.g. "wav", "mp3").
            language: BCP-47 language code.
            enable_punc: Enable punctuation output.
            enable_itn: Enable inverse text normalization.
            poll_interval: Seconds between query polls (default 3).
            poll_max: Maximum total seconds to wait (default 600).
        """
        if audio_bytes is None and audio_url is None:
            raise ValueError("Either audio_bytes or audio_url must be provided")
        if audio_bytes is not None and audio_url is not None:
            raise ValueError("Provide audio_bytes or audio_url, not both")

        task_id = str(uuid4())
        audio_data = base64.b64encode(audio_bytes).decode() if audio_bytes is not None else None
        gateway = self._gateway or SeedSpeechAsrHttpGateway()

        await gateway.submit(
            audio_data=audio_data,
            audio_url=audio_url,
            audio_format=audio_format,
            language=language,
            enable_punc=enable_punc,
            enable_itn=enable_itn,
            request_id=task_id,
        )

        delay = poll_interval
        deadline = time.monotonic() + poll_max
        sequence = 0

        while time.monotonic() < deadline:
            await asyncio.sleep(delay)
            response = await gateway.query(task_id=task_id, sequence=sequence)
            sequence += 1
            if response is not None:
                return self._map_result(response), None
            delay = min(delay * 2, 10.0)

        raise ProviderError(
            NormalizedProviderError(
                provider="seed-speech",
                operation="query_asr_task",
                http_status=None,
                code="TIMEOUT",
                message=f"ASR polling timed out after {poll_max:.0f}s for task {task_id}",
                request_id=task_id,
                retryable=False,
                ambiguous_completion=False,
            )
        )

    @staticmethod
    def _map_result(response: dict[str, Any]) -> TranscriptionResult:
        """Map ASR query response to domain TranscriptionResult."""
        result = response.get("result", {})
        text = result.get("text", "")
        audio_info = response.get("audio_info", {})
        duration_ms = audio_info.get("duration")
        if duration_ms is None:
            additions = result.get("additions", {})
            if isinstance(additions, dict):
                duration_ms = additions.get("duration")
        if duration_ms is not None:
            try:
                duration_ms = int(duration_ms)
            except (TypeError, ValueError):
                duration_ms = None
        utterances = []
        for u in result.get("utterances", []):
            words = [
                TranscriptionWord(
                    text=w.get("text", ""),
                    confidence=w.get("confidence"),
                    start_time_ms=w.get("start_time"),
                    end_time_ms=w.get("end_time"),
                )
                for w in u.get("words", [])
            ]
            utterances.append(
                TranscriptionUtterance(
                    text=u.get("text", ""),
                    start_time_ms=u.get("start_time"),
                    end_time_ms=u.get("end_time"),
                    words=words,
                )
            )
        return TranscriptionResult(text=text, utterances=utterances, duration_ms=duration_ms)
