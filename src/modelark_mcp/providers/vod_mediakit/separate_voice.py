"""Separate-voice submission and task-polling adapter for BytePlus VOD AI MediaKit."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod_mediakit.client import VodMediaKitGateway
from modelark_mcp.providers.vod_mediakit.schemas import (
    SeparateVoiceSubmission,
    SeparateVoiceTask,
    VodMediaKitAcceptedResponse,
    VodMediaKitSeparateVoiceRequest,
    VodMediaKitSeparateVoiceTaskResponse,
)
from modelark_mcp.providers.vod_mediakit.transcode import (
    _normalize_timestamp,
    _sanitize_task_error,
)

_SEPARATE_VOICE_PATH = "/tools/separate-voice"
_TASKS_PATH = "/tasks"
_OPERATION_SUBMIT = "separate_voice"
_OPERATION_GET = "get_audio_separation"


class VodMediaKitSeparateVoiceService:
    """Submit separate-voice tasks and poll their status on the MediaKit surface."""

    def __init__(self, gateway: VodMediaKitGateway | None = None) -> None:
        self._gateway = gateway or VodMediaKitGateway()

    async def submit(self, request: VodMediaKitSeparateVoiceRequest) -> SeparateVoiceSubmission:
        """Submit one separate-voice task; never retries an ambiguous mutation."""
        try:
            response = await self._gateway.post(
                _SEPARATE_VOICE_PATH,
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        except httpx.TimeoutException:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_SUBMIT,
                code="TIMEOUT",
                message=(
                    "MediaKit separate-voice submission timed out after dispatch and may have "
                    "completed. Do not retry blindly; reconcile with BytePlus support using "
                    "request telemetry."
                ),
            ) from None
        except httpx.TransportError:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_SUBMIT,
                code="TRANSPORT_ERROR",
                message=(
                    "MediaKit transport failed after dispatch and completion is unknown. "
                    "Do not retry blindly."
                ),
            ) from None

        header_request_id = VodMediaKitGateway.extract_request_id(response)
        if not 200 <= response.status_code < 300:
            raise VodMediaKitGateway.normalize_error(response, _OPERATION_SUBMIT)

        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod-mediakit",
                    operation=_OPERATION_SUBMIT,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="MediaKit returned a non-JSON success response.",
                    request_id=header_request_id,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        try:
            accepted = VodMediaKitAcceptedResponse.model_validate(body)
        except ValidationError as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod-mediakit",
                    operation=_OPERATION_SUBMIT,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message=(
                        "MediaKit returned an unsupported success response. "
                        "The provider contract must be verified before this response can be accepted."
                    ),
                    request_id=header_request_id,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        return SeparateVoiceSubmission(
            status="accepted",
            request_id=accepted.request_id,
            provider_log_id=header_request_id,
            task_id=accepted.task_id,
        )

    async def get(self, task_id: str) -> SeparateVoiceTask:
        """Poll one separate-voice task and normalize its state."""
        try:
            response = await self._gateway.get(f"{_TASKS_PATH}/{task_id}")
        except httpx.TimeoutException:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TIMEOUT",
                message="MediaKit separate-voice task poll timed out.",
            ) from None
        except httpx.TransportError:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TRANSPORT_ERROR",
                message="MediaKit separate-voice task poll failed to connect.",
            ) from None

        header_request_id = VodMediaKitGateway.extract_request_id(response)
        if not 200 <= response.status_code < 300:
            raise VodMediaKitGateway.normalize_error(response, _OPERATION_GET)

        try:
            body = response.json()
            parsed = VodMediaKitSeparateVoiceTaskResponse.model_validate(body)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod-mediakit",
                    operation=_OPERATION_GET,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="MediaKit returned an unsupported separate-voice task response.",
                    request_id=header_request_id,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        request_id = parsed.request_id or header_request_id
        result = parsed.result

        if parsed.status == "completed":
            if result is None or not any(
                (
                    result.voice_audio_url,
                    result.background_audio_url,
                    result.music_audio_url,
                    result.sfx_audio_url,
                )
            ):
                raise ProviderError(
                    NormalizedProviderError(
                        provider="byteplus-vod-mediakit",
                        operation=_OPERATION_GET,
                        http_status=response.status_code,
                        code="INVALID_RESPONSE",
                        message="MediaKit reported a completed task without a track URL.",
                        request_id=request_id,
                        retryable=False,
                        ambiguous_completion=False,
                    )
                )
            return SeparateVoiceTask(
                task_id=parsed.task_id,
                status="succeeded",
                provider_status=parsed.status,
                request_id=request_id,
                voice_url=result.voice_audio_url,
                background_url=result.background_audio_url,
                music_url=result.music_audio_url,
                sfx_url=result.sfx_audio_url,
                duration_seconds=result.duration,
                created_at=_normalize_timestamp(parsed.created_at),
                finished_at=_normalize_timestamp(parsed.finished_at),
                source_expires_at=_normalize_timestamp(parsed.expires_at),
            )

        if parsed.status == "failed":
            code, message = _sanitize_task_error(
                parsed.error, "MediaKit reported the separate-voice task failed."
            )
            return SeparateVoiceTask(
                task_id=parsed.task_id,
                status="failed",
                provider_status=parsed.status,
                request_id=request_id,
                failure_code=code,
                failure_message=message,
                created_at=_normalize_timestamp(parsed.created_at),
                finished_at=_normalize_timestamp(parsed.finished_at),
            )

        if parsed.status == "running":
            return SeparateVoiceTask(
                task_id=parsed.task_id,
                status="processing",
                provider_status=parsed.status,
                request_id=request_id,
                created_at=_normalize_timestamp(parsed.created_at),
            )

        raise ProviderError(
            NormalizedProviderError(
                provider="byteplus-vod-mediakit",
                operation=_OPERATION_GET,
                http_status=response.status_code,
                code="INVALID_RESPONSE",
                message=(
                    f"MediaKit returned an unrecognized separate-voice status '{parsed.status}'. "
                    "The status contract must be verified before it can be accepted."
                ),
                request_id=request_id,
                retryable=False,
                ambiguous_completion=False,
            )
        )

    async def close(self) -> None:
        """Close the owned/shared HTTP gateway."""
        await self._gateway.close()
