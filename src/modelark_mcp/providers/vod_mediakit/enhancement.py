"""Synchronous enhancement adapter for BytePlus VOD AI MediaKit."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.vod_mediakit.client import (
    VodMediaKitGateway,
    sanitize_provider_message,
)
from modelark_mcp.providers.vod_mediakit.schemas import (
    EnhancementSubmission,
    VodMediaKitAcceptedResponse,
    VodMediaKitEnhancementRequest,
    VodMediaKitProviderResponse,
)

_ENHANCE_PATH = "/tools/enhance-video"
_OPERATION = "enhance_video"


class VodMediaKitEnhancementService:
    """Submit the exact verified video-enhancement profile to MediaKit."""

    def __init__(self, gateway: VodMediaKitGateway | None = None) -> None:
        self._gateway = gateway or VodMediaKitGateway()

    async def enhance(self, request: VodMediaKitEnhancementRequest) -> EnhancementSubmission:
        """Submit one enhancement request without automatic mutation retries."""
        try:
            response = await self._gateway.post(
                _ENHANCE_PATH,
                request.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        except httpx.TimeoutException:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION,
                code="TIMEOUT",
                message=(
                    "MediaKit enhancement timed out after dispatch and may have completed. "
                    "Do not retry blindly; reconcile with BytePlus support using request telemetry."
                ),
            ) from None
        except httpx.TransportError:
            raise VodMediaKitGateway.normalize_ambiguous_transport_error(
                _OPERATION,
                code="TRANSPORT_ERROR",
                message=(
                    "MediaKit transport failed after dispatch and completion is unknown. "
                    "Do not retry blindly."
                ),
            ) from None

        header_request_id = VodMediaKitGateway.extract_request_id(response)
        if not 200 <= response.status_code < 300:
            raise VodMediaKitGateway.normalize_error(response, _OPERATION)

        try:
            body = response.json()
            if (
                isinstance(body, dict)
                and "task_id" in body
                and not {
                    "data",
                    "result",
                }.intersection(body)
            ):
                accepted = VodMediaKitAcceptedResponse.model_validate(body)
                return EnhancementSubmission(
                    status="accepted",
                    request_id=accepted.request_id,
                    provider_log_id=header_request_id,
                    task_id=accepted.task_id,
                )
            provider_response = VodMediaKitProviderResponse.model_validate(body)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise ProviderError(
                NormalizedProviderError(
                    provider="byteplus-vod-mediakit",
                    operation=_OPERATION,
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

        result = provider_response.result
        detail = result.error
        return EnhancementSubmission(
            status="succeeded",
            request_id=provider_response.request_id or result.request_id,
            provider_log_id=header_request_id,
            task_id=result.task_id,
            output_url=result.output_url,
            mime_type=result.mime_type,
            expires_at=result.expires_at,
            output_size_bytes=result.output_size_bytes,
            provider_status=result.status,
            failure_code=detail.code if detail else None,
            failure_message=(
                sanitize_provider_message(detail.message, "MediaKit returned a provider warning.")
                if detail and detail.message
                else None
            ),
        )

    async def close(self) -> None:
        """Close the owned/shared HTTP gateway."""
        await self._gateway.close()
