"""Seed Speech ASR WebSocket binary framing + client.

Pure framing functions encode/decode the 4-byte-header + payload-size + payload
binary protocol. The async client wraps ``websockets`` for connect/send/recv and
normalizes errors into ``ProviderError``.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import ssl
import struct
import uuid
from enum import IntEnum
from typing import Any, ClassVar

import truststore
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidHandshake

from modelark_mcp.config.env import get_settings
from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError, ProviderName
from modelark_mcp.observability.logger import error as log_error

PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001

_DEFAULT_RECV_TIMEOUT = 30.0


class MessageType(IntEnum):
    FULL_CLIENT_REQUEST = 0b0001
    AUDIO_ONLY_REQUEST = 0b0010
    FULL_SERVER_RESPONSE = 0b1001
    SERVER_ERROR = 0b1111


class Serialization(IntEnum):
    NONE = 0b0000
    JSON = 0b0001


class Compression(IntEnum):
    NONE = 0b0000
    GZIP = 0b0001


_FLAG_LAST_CHUNK = 0b0010

_RETRYABLE_ASR_CODES = frozenset({1003, 1005, 1020, 1021})


def _build_header(
    msg_type: IntEnum,
    flags: int = 0,
    serialization: IntEnum = Serialization.NONE,
    compression: IntEnum = Compression.GZIP,
) -> bytes:
    byte0 = (PROTOCOL_VERSION << 4) | HEADER_SIZE
    byte1 = (msg_type << 4) | (flags & 0x0F)
    byte2 = (serialization << 4) | compression
    return bytes([byte0, byte1, byte2, 0x00])


def encode_full_client_request(config: dict[str, Any]) -> bytes:
    """Encode JSON config: header + size + gzip(json)."""
    payload = gzip.compress(json.dumps(config).encode("utf-8"))
    header = _build_header(
        MessageType.FULL_CLIENT_REQUEST,
        serialization=Serialization.JSON,
    )
    return header + struct.pack(">I", len(payload)) + payload


def encode_audio_chunk(data: bytes, *, is_last: bool = False) -> bytes:
    """Encode raw audio: header + size + gzip(data)."""
    payload = gzip.compress(data)
    flags = _FLAG_LAST_CHUNK if is_last else 0
    header = _build_header(MessageType.AUDIO_ONLY_REQUEST, flags=flags)
    return header + struct.pack(">I", len(payload)) + payload


def decode_server_message(frame: bytes) -> tuple[MessageType, Any]:
    """Decode a server frame → (msg_type, payload).

    FULL_SERVER_RESPONSE → (type, parsed_dict); SERVER_ERROR → (type, (code, msg)).
    """
    if len(frame) < 9:
        raise ValueError(f"ASR server frame too short: expected ≥9 bytes, got {len(frame)}")
    msg_type = MessageType((frame[1] >> 4) & 0x0F)
    serialization = Serialization((frame[2] >> 4) & 0x0F)
    compression = Compression(frame[2] & 0x0F)
    payload_size = struct.unpack(">I", frame[4:8])[0]
    payload = frame[8 : 8 + payload_size]
    if compression == Compression.GZIP:
        payload = gzip.decompress(payload)
    if msg_type == MessageType.SERVER_ERROR:
        code = struct.unpack(">I", payload[:4])[0]
        msg_len = struct.unpack(">I", payload[4:8])[0]
        message = payload[8 : 8 + msg_len].decode("utf-8", errors="replace")
        return msg_type, (code, message)
    if serialization == Serialization.JSON:
        return msg_type, json.loads(payload.decode("utf-8"))
    return msg_type, payload


class SeedSpeechAsrWsClient:
    """Async WebSocket client for Seed Speech ASR (owns the socket)."""

    PROVIDER: ClassVar[ProviderName] = "seed-speech"

    def __init__(
        self,
        *,
        ws_url: str,
        api_key: str,
        resource_id: str = "volc.seedasr.sauc.duration",
        connect_timeout: float,
        recv_timeout: float = _DEFAULT_RECV_TIMEOUT,
    ) -> None:
        self._ws_url = ws_url
        self._api_key = api_key
        self._resource_id = resource_id
        self._connect_timeout = connect_timeout
        self._recv_timeout = recv_timeout
        self._ws: Any = None

    async def __aenter__(self) -> SeedSpeechAsrWsClient:
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            self._ws = await connect(
                self._ws_url,
                additional_headers={
                    "X-Api-Key": self._api_key,
                    "X-Api-Resource-Id": self._resource_id,
                    "X-Api-Request-Id": str(uuid.uuid4()),
                    "X-Api-Sequence": "-1",
                },
                ssl=ssl_context,
                open_timeout=self._connect_timeout,
            )
        except TimeoutError:
            raise self._connection_error("CONNECTION_TIMEOUT", retryable=True) from None
        except InvalidHandshake as exc:
            status_str = str(exc)
            retryable = "5" in status_str and (
                "502" in status_str or "503" in status_str or "504" in status_str
            )
            raise self._connection_error(
                "HANDSHAKE_FAILED",
                retryable=retryable,
            ) from exc
        except ssl.SSLError as exc:
            raise self._connection_error("TLS_ERROR", retryable=False) from exc
        except OSError as exc:
            raise self._connection_error("CONNECTION_FAILED", retryable=True) from exc
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_config(self, config: dict[str, Any]) -> None:
        await self._ws.send(encode_full_client_request(config))

    async def send_audio(self, chunk: bytes, *, is_last: bool = False) -> None:
        await self._ws.send(encode_audio_chunk(chunk, is_last=is_last))

    async def recv(self) -> tuple[MessageType, Any]:
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self._recv_timeout)
        return decode_server_message(raw)

    @classmethod
    def from_settings(cls) -> SeedSpeechAsrWsClient:
        settings = get_settings()
        return cls(
            ws_url=settings.seed_speech_asr_ws_url,
            api_key=settings.seed_audio_api_key,
            resource_id=settings.seed_speech_asr_resource_id,
            connect_timeout=settings.connect_timeout_ms / 1000,
        )

    @classmethod
    def _connection_error(cls, code: str, *, retryable: bool) -> ProviderError:
        normalized = NormalizedProviderError(
            provider=cls.PROVIDER,
            operation="connect",
            code=code,
            message=f"WebSocket connection failed: {code}",
            retryable=retryable,
            ambiguous_completion=False,
        )
        log_error(
            "seed_speech_asr_connect_error",
            code=code,
            retryable=retryable,
        )
        return ProviderError(normalized)

    @classmethod
    def normalize_error(cls, code: int, message: str, operation: str) -> ProviderError:
        retryable = code in _RETRYABLE_ASR_CODES
        normalized = NormalizedProviderError(
            provider=cls.PROVIDER,
            operation=operation,
            code=str(code) if code else None,
            message=message,
            retryable=retryable,
            ambiguous_completion=False,
        )
        log_error(
            "seed_speech_asr_error",
            operation=operation,
            code=code,
            retryable=retryable,
            error_message=message,
        )
        return ProviderError(normalized)
