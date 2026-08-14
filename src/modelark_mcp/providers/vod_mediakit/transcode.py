"""Transcode-submission and task-polling adapter for BytePlus VOD AI MediaKit."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from pydantic import ValidationError

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod_mediakit.client import (
    VodMediaKitGateway,
    sanitize_provider_message,
)
from modelark_mcp.providers.vod_mediakit.schemas import (
    TranscodeSubmission,
    TranscodeTask,
    VodMediaKitAcceptedResponse,
    VodMediaKitTranscodeRequest,
    VodMediaKitTranscodeTaskResponse,
)

if TYPE_CHECKING:
    from typing import Any

_TRANSCODE_PATH = "/tools/transcode-video"
_TASKS_PATH = "/tasks"
_OPERATION_SUBMIT = "transcode_video"
_OPERATION_GET = "get_transcode_task"


def _normalize_timestamp(value: str | int | None) -> str | None:
    """Normalize a provider Unix-seconds or ISO-8601 timestamp to ISO-8601 UTC."""
    if value is None:
        return None
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        if value.strip().isdigit():
            return _normalize_timestamp(int(value.strip()))
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None


def _sanitize_task_error(detail: Any, fallback: str) -> tuple[str | None, str | None]:
    """Extract a safe failure code and message from a task error detail."""
    if detail is None:
        return None, None
    code = getattr(detail, "code", None)
    message = getattr(detail, "message", None)
    if not message:
        return None, None
    return (
        code if isinstance(code, str) and code else None,
        sanitize_provider_message(message, fallback),
    )


class VodMediaKitTranscodeService:
    """Submit transcode tasks and poll their status on the MediaKit surface."""

    def __init__(self, gateway: VodMediaKitGateway | None = None) -> None:
        self._gateway = gateway or VodMediaKitGateway()

    async def submit(self, request: VodMediaKitTranscodeRequest) -> TranscodeSubmission:
        """Submit one transcode task; never retries an ambiguous mutation."""
        try:
            response = await self._gateway.post(
                _TRANSCODE_PATH,
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        except httpx.TimeoutException:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_SUBMIT,
                code="TIMEOUT",
                message=(
                    "MediaKit transcode submission timed out after dispatch and may have completed. "
                    "Do not retry blindly; reconcile with BytePlus support using request telemetry."
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

        return TranscodeSubmission(
            status="accepted",
            request_id=accepted.request_id,
            provider_log_id=header_request_id,
            task_id=accepted.task_id,
        )

    async def get(self, task_id: str) -> TranscodeTask:
        """Poll one transcode task and normalize its state."""
        try:
            response = await self._gateway.get(f"{_TASKS_PATH}/{task_id}")
        except httpx.TimeoutException:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TIMEOUT",
                message="MediaKit transcode task poll timed out.",
            ) from None
        except httpx.TransportError:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TRANSPORT_ERROR",
                message="MediaKit transcode task poll failed to connect.",
            ) from None

        header_request_id = VodMediaKitGateway.extract_request_id(response)
        if not 200 <= response.status_code < 300:
            raise VodMediaKitGateway.normalize_error(response, _OPERATION_GET)

        try:
            body = response.json()
            parsed = VodMediaKitTranscodeTaskResponse.model_validate(body)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod-mediakit",
                    operation=_OPERATION_GET,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="MediaKit returned an unsupported task response.",
                    request_id=header_request_id,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        request_id = parsed.request_id or header_request_id
        task_id = parsed.task_id
        result = parsed.result

        if parsed.status == "completed":
            if result is None or result.video_url is None:
                raise ProviderError(
                    NormalizedProviderError(
                        provider="byteplus-vod-mediakit",
                        operation=_OPERATION_GET,
                        http_status=response.status_code,
                        code="INVALID_RESPONSE",
                        message="MediaKit reported a completed task without an output URL.",
                        request_id=request_id,
                        retryable=False,
                        ambiguous_completion=False,
                    )
                )
            return TranscodeTask(
                task_id=task_id,
                status="succeeded",
                provider_status=parsed.status,
                request_id=request_id,
                output_url=result.video_url,
                duration_seconds=result.duration,
                resolution=result.resolution,
                video_codec=result.video_codec,
                created_at=_normalize_timestamp(parsed.created_at),
                finished_at=_normalize_timestamp(parsed.finished_at),
                source_expires_at=_normalize_timestamp(parsed.expires_at),
            )

        if parsed.status == "failed":
            code, message = _sanitize_task_error(
                parsed.error, "MediaKit reported the transcode task failed."
            )
            return TranscodeTask(
                task_id=task_id,
                status="failed",
                provider_status=parsed.status,
                request_id=request_id,
                failure_code=code,
                failure_message=message,
                created_at=_normalize_timestamp(parsed.created_at),
                finished_at=_normalize_timestamp(parsed.finished_at),
            )

        if parsed.status == "running":
            return TranscodeTask(
                task_id=task_id,
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
                    f"MediaKit returned an unrecognized transcode status '{parsed.status}'. "
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
