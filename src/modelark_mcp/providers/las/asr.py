"""LAS ASR adapter — speech-to-text through BytePlus Lake AI Service.

Translates domain input models to provider DTOs, calls the LAS gateway for
submit and poll operations, and maps provider responses to domain output
models.
"""

from __future__ import annotations

from typing import Any

import httpx

from modelark_mcp.providers.las.client import LasGateway
from modelark_mcp.providers.las.schemas import (
    LasAsrPollResponse,
    LasAsrSubmitRequest,
    LasAsrSubmitResponse,
)


class LasAsrService:
    """Service layer for LAS ASR (speech-to-text)."""

    def __init__(self, gateway: LasGateway | None = None) -> None:
        self._gateway = gateway or LasGateway()

    async def submit(
        self,
        request: LasAsrSubmitRequest,
    ) -> tuple[LasAsrSubmitResponse, str | None]:
        """Call ``POST /api/v1/submit``.

        Returns ``(response, request_id)`` where ``request_id`` is extracted
        from the parsed response body (``metadata.request_id``), not from
        response headers.
        """
        try:
            response = await self._gateway.post(
                "/api/v1/submit",
                request.model_dump(exclude_none=True),
            )
        except httpx.TimeoutException:
            raise LasGateway.normalize_timeout("submit_asr_task") from None
        except httpx.ConnectError as exc:
            raise LasGateway.normalize_connection_error("submit_asr_task", exc) from exc
        except httpx.TransportError as exc:
            raise LasGateway.normalize_transport_error("submit_asr_task", exc) from exc

        if response.status_code >= 400:
            raise LasGateway.normalize_error(response, "submit_asr_task")

        body = response.json()
        parsed = LasAsrSubmitResponse.model_validate(body)
        return parsed, parsed.metadata.request_id

    async def poll(
        self,
        task_id: str,
        operator_id: str = "las_asr_pro",
        operator_version: str = "v1",
    ) -> tuple[LasAsrPollResponse, str | None]:
        """Call ``POST /api/v1/poll``.

        Returns ``(response, request_id)`` where ``request_id`` is extracted
        from the parsed response body (``metadata.request_id``).
        """
        request_body: dict[str, Any] = {
            "operator_id": operator_id,
            "operator_version": operator_version,
            "task_id": task_id,
        }
        try:
            response = await self._gateway.post("/api/v1/poll", request_body)
        except httpx.TimeoutException:
            raise LasGateway.normalize_timeout("poll_asr_task") from None
        except httpx.ConnectError as exc:
            raise LasGateway.normalize_connection_error("poll_asr_task", exc) from exc
        except httpx.TransportError as exc:
            raise LasGateway.normalize_transport_error("poll_asr_task", exc) from exc

        if response.status_code >= 400:
            raise LasGateway.normalize_error(response, "poll_asr_task")

        body = response.json()
        parsed = LasAsrPollResponse.model_validate(body)
        return parsed, parsed.metadata.request_id

    @staticmethod
    def build_submit_request(
        *,
        audio_url: str,
        audio_format: str,
        resource: str | None = "bigasr",
        model_name: str = "bigmodel",
        enable_punc: bool | None = None,
        enable_itn: bool | None = None,
        enable_speaker_info: bool | None = None,
        enable_lid: bool | None = None,
        show_utterances: bool | None = None,
        show_words: bool | None = None,
        operator_id: str = "las_asr_pro",
        operator_version: str = "v1",
    ) -> LasAsrSubmitRequest:
        """Build a submit request from domain-level parameters."""
        from modelark_mcp.providers.las.schemas import (
            LasAsrRequestConfig,
            LasAsrSubmitData,
            LasAudioInput,
        )

        config = LasAsrRequestConfig(
            model_name=model_name,
            enable_punc=enable_punc,
            enable_itn=enable_itn,
            enable_speaker_info=enable_speaker_info,
            enable_lid=enable_lid,
            show_utterances=show_utterances,
            show_words=show_words,
        )

        data = LasAsrSubmitData(
            audio=LasAudioInput(url=audio_url, format=audio_format),
            request=config,
            resource=resource,
        )

        return LasAsrSubmitRequest(
            operator_id=operator_id,
            operator_version=operator_version,
            data=data,
        )

    @staticmethod
    def derive_operator_version(operator_id: str) -> str:
        """Derive the operator version from the operator ID.

        ``las_asr_pro`` → ``v1``, ``las_asr`` → ``v2``.
        """
        if operator_id == "las_asr":
            return "v2"
        return "v1"

    async def close(self) -> None:
        await self._gateway.close()
