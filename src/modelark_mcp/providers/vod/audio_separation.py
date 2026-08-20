"""Audio-separation submit/poll adapter for the BytePlus VOD OpenAPI."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod.client import VodOpenApiGateway
from modelark_mcp.providers.vod.schemas import (
    AudioSeparationSubmission,
    AudioSeparationTask,
    VodGetExecutionResponse,
    VodStartExecutionRequest,
    VodStartExecutionResponse,
)

_OPERATION_SUBMIT = "start_audio_separation"
_OPERATION_GET = "get_audio_separation"

_FAILED_STATUSES = frozenset({"Fail", "Failed", "Error", "Terminated", "Timeout"})


class VodAudioSeparationService:
    """Submit and poll VOD OpenAPI ``AudioExtract`` execution tasks."""

    def __init__(self, gateway: VodOpenApiGateway | None = None) -> None:
        self._gateway = gateway or VodOpenApiGateway()

    async def submit(self, request: VodStartExecutionRequest) -> AudioSeparationSubmission:
        """Submit one separation task; never retries an ambiguous mutation."""
        try:
            response = await self._gateway.post_json(
                {"Action": "StartExecution", "Version": VodOpenApiGateway.VERSION},
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        except httpx.TimeoutException:
            raise VodOpenApiGateway.normalize_ambiguous_transport_error(
                _OPERATION_SUBMIT,
                code="TIMEOUT",
                message=(
                    "VOD OpenAPI separation submission timed out after dispatch and may have "
                    "completed. Do not retry blindly; reconcile with BytePlus support."
                ),
            ) from None
        except httpx.TransportError:
            raise VodOpenApiGateway.normalize_ambiguous_transport_error(
                _OPERATION_SUBMIT,
                code="TRANSPORT_ERROR",
                message=(
                    "VOD OpenAPI transport failed after dispatch and completion is unknown. "
                    "Do not retry blindly."
                ),
            ) from None

        if not 200 <= response.status_code < 300:
            raise VodOpenApiGateway.normalize_error(response, _OPERATION_SUBMIT)

        try:
            body = response.json()
            parsed = VodStartExecutionResponse.model_validate(body)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod",
                    operation=_OPERATION_SUBMIT,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message=(
                        "VOD OpenAPI returned an unsupported StartExecution response. "
                        "The provider contract must be verified before this response can be accepted."
                    ),
                    request_id=None,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        if parsed.result is None or not parsed.result.run_id:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod",
                    operation=_OPERATION_SUBMIT,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="VOD OpenAPI returned a StartExecution response without a RunId.",
                    request_id=(
                        parsed.response_metadata.request_id if parsed.response_metadata else None
                    ),
                    retryable=False,
                    ambiguous_completion=False,
                )
            )

        request_id = parsed.response_metadata.request_id if parsed.response_metadata else None
        return AudioSeparationSubmission(
            status="accepted",
            request_id=request_id,
            run_id=parsed.result.run_id,
        )

    async def get(self, run_id: str) -> AudioSeparationTask:
        """Poll one separation task and normalize its state."""
        try:
            response = await self._gateway.get(
                {
                    "Action": "GetExecution",
                    "Version": VodOpenApiGateway.VERSION,
                    "RunId": run_id,
                }
            )
        except httpx.TimeoutException:
            raise VodOpenApiGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TIMEOUT",
                message="VOD OpenAPI separation task poll timed out.",
            ) from None
        except httpx.TransportError:
            raise VodOpenApiGateway.normalize_ambiguous_transport_error(
                _OPERATION_GET,
                code="TRANSPORT_ERROR",
                message="VOD OpenAPI separation task poll failed to connect.",
            ) from None

        if not 200 <= response.status_code < 300:
            raise VodOpenApiGateway.normalize_error(response, _OPERATION_GET)

        try:
            body = response.json()
            parsed = VodGetExecutionResponse.model_validate(body)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod",
                    operation=_OPERATION_GET,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="VOD OpenAPI returned an unsupported GetExecution response.",
                    request_id=None,
                    retryable=False,
                    ambiguous_completion=False,
                )
            ) from exc

        result = parsed.result
        if result is None or not result.run_id:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod",
                    operation=_OPERATION_GET,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="VOD OpenAPI returned a GetExecution response without a RunId.",
                    request_id=(
                        parsed.response_metadata.request_id if parsed.response_metadata else None
                    ),
                    retryable=False,
                    ambiguous_completion=False,
                )
            )

        request_id = parsed.response_metadata.request_id if parsed.response_metadata else None
        status = (result.status or "").strip()
        audio_extract = None
        if result.output is not None and result.output.task is not None:
            audio_extract = result.output.task.audio_extract

        if status == "Success":
            if audio_extract is None or not (audio_extract.voice and audio_extract.voice.file_name):
                raise ProviderError(
                    NormalizedProviderError(
                        provider="byteplus-vod",
                        operation=_OPERATION_GET,
                        http_status=response.status_code,
                        code="INVALID_RESPONSE",
                        message=(
                            "VOD OpenAPI reported a successful task without a voice FileName."
                        ),
                        request_id=request_id,
                        retryable=False,
                        ambiguous_completion=False,
                    )
                )
            voice = audio_extract.voice
            background = audio_extract.background
            return AudioSeparationTask(
                run_id=result.run_id,
                status="succeeded",
                provider_status=status,
                request_id=request_id,
                duration_seconds=audio_extract.duration,
                voice_file_name=voice.file_name,
                voice_size_bytes=voice.size,
                background_file_name=background.file_name if background else None,
                background_size_bytes=background.size if background else None,
            )

        if status in _FAILED_STATUSES:
            code = result.code or "FAILED"
            return AudioSeparationTask(
                run_id=result.run_id,
                status="failed",
                provider_status=status or None,
                request_id=request_id,
                failure_code=code,
                failure_message=(
                    f"VOD OpenAPI reported the separation task failed with status '{status}'."
                ),
            )

        if not status:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod",
                    operation=_OPERATION_GET,
                    http_status=response.status_code,
                    code="INVALID_RESPONSE",
                    message="VOD OpenAPI returned a GetExecution result without a Status.",
                    request_id=request_id,
                    retryable=False,
                    ambiguous_completion=False,
                )
            )

        return AudioSeparationTask(
            run_id=result.run_id,
            status="processing",
            provider_status=status,
            request_id=request_id,
        )

    async def close(self) -> None:
        """Close the owned/shared HTTP gateway."""
        await self._gateway.close()
