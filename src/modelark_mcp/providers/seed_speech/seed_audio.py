"""Seed Audio adapter — full-scene audio generation through Seed Speech.

Translates domain input models to provider DTOs, calls the Seed Speech
gateway, and maps provider responses to domain output models.
"""

from __future__ import annotations

from typing import Any

import httpx

from modelark_mcp.domain.models import Subtitle, SubtitleUtterance, SubtitleWord
from modelark_mcp.providers.seed_speech.client import SeedSpeechGateway
from modelark_mcp.providers.seed_speech.schemas import (
    SeedAudioProviderRequest,
    SeedAudioProviderResponse,
)


class SeedAudioService:
    """Service layer for Seed Audio generation."""

    def __init__(self, gateway: SeedSpeechGateway | None = None) -> None:
        self._gateway = gateway or SeedSpeechGateway()

    async def generate(
        self,
        request: SeedAudioProviderRequest,
        *,
        request_id: str | None = None,
    ) -> tuple[SeedAudioProviderResponse, str | None]:
        """Call ``POST /api/v3/tts/create``.

        Returns ``(response, log_id)`` where ``log_id`` is the ``X-Tt-Logid``
        diagnostic header.
        Raises ``NormalizedProviderError`` on failure.
        """
        try:
            response = await self._gateway.post(
                "/api/v3/tts/create",
                request.to_api_dict(),
                request_id=request_id,
            )
        except httpx.TimeoutException:
            raise SeedSpeechGateway.normalize_timeout("generate_audio") from None
        except httpx.ConnectError as exc:
            raise SeedSpeechGateway.normalize_connection_error("generate_audio", exc) from exc
        except httpx.TransportError as exc:
            raise SeedSpeechGateway.normalize_transport_error("generate_audio", exc) from exc

        log_id = SeedSpeechGateway.extract_log_id(response)

        if response.status_code >= 400:
            raise SeedSpeechGateway.normalize_error(response, "generate_audio")

        body = response.json()
        return SeedAudioProviderResponse.model_validate(body), log_id

    @staticmethod
    def build_request(
        *,
        text_prompt: str,
        references: list[dict[str, Any]] | None = None,
        output: dict[str, Any] | None = None,
        watermark: dict[str, Any] | None = None,
    ) -> SeedAudioProviderRequest:
        """Build a provider request from domain-level parameters."""
        return SeedAudioProviderRequest(
            model="seed-audio-1.0",
            text_prompt=text_prompt,
            references=references,
            output=output,
            watermark=watermark,
        )

    @staticmethod
    def build_references(
        audio_refs: list[dict[str, Any]] | None,
        image_ref: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Build the provider ``references[]`` array.

        Audio references use ``speaker``, ``audio_url``, or ``audio_data``.
        Image references use ``image_url`` or ``image_data``.
        Audio and image references are mutually exclusive.
        """
        refs: list[dict[str, Any]] = []

        if audio_refs:
            for ref in audio_refs:
                kind = ref.get("kind")
                entry: dict[str, Any] = {}
                if kind == "speaker":
                    entry["speaker"] = ref.get("speaker_id")
                elif kind == "url":
                    entry["audio_url"] = ref.get("url")
                    if ref.get("mime_type"):
                        entry["mime_type"] = ref["mime_type"]
                elif kind == "base64":
                    entry["audio_data"] = ref.get("data")
                    if ref.get("mime_type"):
                        entry["mime_type"] = ref["mime_type"]
                if entry:
                    refs.append(entry)

        if image_ref:
            img_entry: dict[str, Any] = {}
            if image_ref.get("kind") == "url":
                img_entry["image_url"] = image_ref.get("url")
            elif image_ref.get("kind") == "base64":
                img_entry["image_data"] = image_ref.get("data")
            if image_ref.get("mime_type"):
                img_entry["mime_type"] = image_ref["mime_type"]
            if img_entry:
                refs.append(img_entry)

        return refs

    @staticmethod
    def extract_subtitle(
        response: SeedAudioProviderResponse,
    ) -> Subtitle | None:
        """Extract subtitle data from the provider response."""
        if response.subtitle is None:
            return None
        return Subtitle(
            utterances=[
                SubtitleUtterance.model_validate(item) for item in response.subtitle.utterances
            ],
            words=[SubtitleWord.model_validate(item) for item in response.subtitle.words],
        )

    async def close(self) -> None:
        await self._gateway.close()
