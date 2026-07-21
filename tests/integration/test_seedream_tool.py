"""Integration tests for the ``seedream_generate_image`` tool handler.

Exercises the full path: input validation → capability registry check →
provider call (mocked) → artifact persistence → structured output.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.modelark.schemas import SeedreamProviderResponse
from modelark_mcp.providers.modelark.seedream import SeedreamService
from modelark_mcp.tools.seedream_generate_image import (
    SeedreamGenerateInput,
    SeedreamGenerateOutput,
    seedream_generate_image,
)
from tests.integration.conftest import FakeContext


def _patch_seedream_service(monkeypatch: pytest.MonkeyPatch, response_data: dict[str, Any]) -> None:
    """Patch SeedreamService.generate to return a fixed response."""

    async def mock_generate(
        self: SeedreamService, request: Any
    ) -> tuple[SeedreamProviderResponse, str | None]:
        response = SeedreamProviderResponse.model_validate(response_data)
        return response, "req-test-456"

    monkeypatch.setattr(SeedreamService, "generate", mock_generate)


class TestSeedreamGenerateImageTool:
    """Full-path integration tests for seedream_generate_image."""

    async def test_text_to_image_with_url_persistence(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_seedream_service(
            monkeypatch,
            {
                "created": 1721400000,
                "data": [{"url": "https://tos-ap-southeast.bytepluses.com/out.png"}],
                "usage": {"prompt_tokens": 10, "total_tokens": 20},
            },
        )

        # Mock the HTTP download for copy_from_trusted_url.
        with (
            patch("modelark_mcp.server.get_artifact_store", return_value=temp_store),
            patch("modelark_mcp.artifacts.filesystem_store.validate_url"),
            respx.mock,
        ):
            respx.get("https://tos-ap-southeast.bytepluses.com/out.png").mock(
                return_value=httpx.Response(
                    200, content=b"fake-png-data", headers={"content-type": "image/png"}
                )
            )

            result = await seedream_generate_image(
                SeedreamGenerateInput(prompt="a red circle"), fake_ctx
            )

        assert isinstance(result, SeedreamGenerateOutput)
        assert result.provider == "byteplus-modelark"
        assert result.model == "dola-seedream-5-0-pro-260628"
        assert len(result.artifacts) == 1
        assert result.artifacts[0].media_type == "image"
        assert result.usage.total_tokens == 20

    async def test_b64_json_persistence(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        temp_store: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import base64

        img_b64 = base64.b64encode(b"fake-image-bytes").decode()
        _patch_seedream_service(
            monkeypatch,
            {"created": 1721400000, "data": [{"b64_json": img_b64}]},
        )

        with patch("modelark_mcp.server.get_artifact_store", return_value=temp_store):
            result = await seedream_generate_image(
                SeedreamGenerateInput(prompt="test image"), fake_ctx
            )

        assert len(result.artifacts) == 1
        assert result.artifacts[0].uri.startswith("seed-media://artifacts/")

        # Verify stored data.
        stored = await temp_store.get(result.artifacts[0].id)
        assert stored.data == b"fake-image-bytes"

    async def test_no_persistence_returns_provider_url(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_seedream_service(
            monkeypatch,
            {
                "created": 1721400000,
                "data": [{"url": "https://tos-ap-southeast.bytepluses.com/img.png"}],
            },
        )

        with patch("modelark_mcp.server.get_artifact_store"):
            result = await seedream_generate_image(
                SeedreamGenerateInput(prompt="test", persist=False), fake_ctx
            )

        assert result.artifacts[0].id == "provider-url"
        assert result.artifacts[0].uri == "https://tos-ap-southeast.bytepluses.com/img.png"

    async def test_batch_rejected_for_pro_model(
        self,
        test_env: None,
        fake_ctx: FakeContext,
    ) -> None:
        with pytest.raises(ValueError, match="does not support batch"):
            await seedream_generate_image(
                SeedreamGenerateInput(prompt="test", max_images=3), fake_ctx
            )

    async def test_too_many_references_rejected(
        self,
        test_env: None,
        fake_ctx: FakeContext,
    ) -> None:
        from modelark_mcp.domain.media import MediaSource, MediaSourceKind

        images = [
            MediaSource(kind=MediaSourceKind.url, url=f"https://cdn.example.com/{i}.png")
            for i in range(11)
        ]
        with pytest.raises(ValueError, match="at most 10"):
            await seedream_generate_image(
                SeedreamGenerateInput(prompt="test", images=images), fake_ctx
            )

    async def test_provider_error_propagates(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def mock_generate(
            self: SeedreamService, request: Any
        ) -> tuple[SeedreamProviderResponse, str | None]:
            raise ProviderError(
                NormalizedProviderError(
                    provider="modelark",
                    operation="generate_image",
                    http_status=403,
                    code="FORBIDDEN",
                    message="model not activated",
                    retryable=False,
                )
            )

        monkeypatch.setattr(SeedreamService, "generate", mock_generate)

        with pytest.raises(ProviderError) as exc_info:
            await seedream_generate_image(SeedreamGenerateInput(prompt="test"), fake_ctx)
        assert exc_info.value.http_status == 403
