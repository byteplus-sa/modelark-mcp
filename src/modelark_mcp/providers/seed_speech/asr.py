"""Seed Speech ASR adapter — speech-to-text over WebSocket.

Orchestrates the WS binary protocol: sends config, streams audio chunks,
buffers partial results, and maps the final response to a domain
``TranscriptionResult``. Streaming is fully hidden from the caller — one call,
one complete result.
"""

from __future__ import annotations

import asyncio

from modelark_mcp.domain.transcription import (
    TranscriptionResult,
    TranscriptionUtterance,
    TranscriptionWord,
)
from modelark_mcp.providers.seed_speech.asr_schemas import (
    AsrAudioConfig,
    AsrFullClientRequest,
    AsrRequestConfig,
    AsrServerResponse,
)
from modelark_mcp.providers.seed_speech.asr_ws import (
    MessageType,
    SeedSpeechAsrWsClient,
)

_SESSION_TIMEOUT = 3600.0


class SeedSpeechAsrService:
    """Service layer for Seed Speech ASR (speech-to-text)."""

    def __init__(self, client: SeedSpeechAsrWsClient | None = None) -> None:
        self._client = client

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        audio_format: str,
        language: str = "en-US",
        enable_punc: bool | None = None,
        enable_itn: bool | None = None,
        chunk_bytes: int = 16384,
        session_timeout: float = _SESSION_TIMEOUT,
    ) -> tuple[TranscriptionResult, str | None]:
        """Transcribe audio via one WS session. Returns ``(result, log_id)``.

        Blocks until the server emits the final response after the last audio
        chunk. All partial responses are buffered and discarded; only the
        final, complete transcription is returned.
        """
        config = self.build_client_request(
            audio_format=audio_format,
            language=language,
            enable_punc=enable_punc,
            enable_itn=enable_itn,
        )
        client = self._client or SeedSpeechAsrWsClient.from_settings()

        async def _run() -> tuple[TranscriptionResult, str | None]:
            latest: AsrServerResponse | None = None
            async with client:
                await client.send_config(config.model_dump())
                ack_type, ack_payload = await client.recv()
                if ack_type == MessageType.SERVER_ERROR:
                    code, message = ack_payload
                    raise SeedSpeechAsrWsClient.normalize_error(
                        code, message, "configure"
                    )
                for offset in range(0, len(audio_bytes), chunk_bytes):
                    chunk = audio_bytes[offset : offset + chunk_bytes]
                    is_last = offset + chunk_bytes >= len(audio_bytes)
                    await client.send_audio(chunk, is_last=is_last)
                    msg_type, payload = await client.recv()
                    if msg_type == MessageType.SERVER_ERROR:
                        code, message = payload
                        raise SeedSpeechAsrWsClient.normalize_error(
                            code, message, "transcribe"
                        )
                    latest = AsrServerResponse.model_validate(payload)

            if latest is None or latest.result is None:
                return TranscriptionResult(text=""), None
            return self.map_result(latest), None

        return await asyncio.wait_for(_run(), timeout=session_timeout)

    @staticmethod
    def build_client_request(
        *,
        audio_format: str,
        language: str,
        enable_punc: bool | None,
        enable_itn: bool | None,
    ) -> AsrFullClientRequest:
        return AsrFullClientRequest(
            audio=AsrAudioConfig(format=audio_format, language=language),
            request=AsrRequestConfig(
                enable_punc=enable_punc,
                enable_itn=enable_itn,
                show_utterances=True,
            ),
        )

    @staticmethod
    def map_result(response: AsrServerResponse) -> TranscriptionResult:
        r = response.result
        if r is None:
            return TranscriptionResult(text="")
        utterances = [
            TranscriptionUtterance(
                text=u.text,
                start_time_ms=u.start_time,
                end_time_ms=u.end_time,
                words=[
                    TranscriptionWord(
                        text=w.text,
                        confidence=w.confidence,
                        start_time_ms=w.start_time,
                        end_time_ms=w.end_time,
                    )
                    for w in u.words
                ],
            )
            for u in r.utterances
            if u.definite is not False
        ]
        return TranscriptionResult(text=r.text, utterances=utterances)
