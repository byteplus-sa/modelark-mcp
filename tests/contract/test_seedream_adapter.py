"""Contract tests for the Seedream adapter (image generation).

Tests request building, response parsing, usage extraction, and partial
failure handling against redacted fixture shapes.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.providers.modelark.client import ModelArkGateway
from modelark_mcp.providers.modelark.seedream import SeedreamService

MODELARK_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"


@pytest.fixture
def service() -> SeedreamService:
    """Create a SeedreamService with a test gateway."""
    gateway = ModelArkGateway(
        api_key="sk-test-key",  # pragma: allowlist secret
        base_url=MODELARK_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )
    return SeedreamService(gateway=gateway)


class TestSeedreamRequestBuilding:
    """Tests for provider request construction."""

    def test_text_to_image_request(self) -> None:
        request = SeedreamService.build_request(
            model="dola-seedream-5-0-pro-260628",
            prompt="a cat sitting on a mat",
        )
        assert request.model == "dola-seedream-5-0-pro-260628"
        assert request.prompt == "a cat sitting on a mat"
        assert request.image is None
        assert request.stream is False
        assert request.sequential_image_generation is None

    def test_edit_request_with_single_image_url(self) -> None:
        request = SeedreamService.build_request(
            model="dola-seedream-5-0-pro-260628",
            prompt="make it night time",
            images=[{"url": "https://cdn.example.com/input.png"}],
        )
        assert request.image == "https://cdn.example.com/input.png"

    def test_edit_request_with_multiple_images(self) -> None:
        request = SeedreamService.build_request(
            model="seedream-5-0-260128",
            prompt="combine these",
            images=[
                {"url": "https://cdn.example.com/a.png"},
                {"url": "https://cdn.example.com/b.png"},
            ],
        )
        assert isinstance(request.image, list)
        assert len(request.image) == 2

    def test_batch_request_derives_sequential(self) -> None:
        request = SeedreamService.build_request(
            model="seedream-5-0-260128",
            prompt="generate 3 variants",
            max_images=3,
        )
        assert request.sequential_image_generation == "auto"
        assert request.sequential_image_generation_options == {"max_images": 3}

    def test_single_image_does_not_set_sequential(self) -> None:
        request = SeedreamService.build_request(
            model="dola-seedream-5-0-pro-260628",
            prompt="single image",
            max_images=1,
        )
        assert request.sequential_image_generation is None

    def test_prompt_optimization(self) -> None:
        request = SeedreamService.build_request(
            model="dola-seedream-5-0-pro-260628",
            prompt="optimized prompt",
            prompt_optimization="fast",
        )
        assert request.optimize_prompt_options == {"mode": "fast"}

    def test_stream_always_false(self) -> None:
        request = SeedreamService.build_request(
            model="seedream-5-0-260128",
            prompt="test",
        )
        assert request.stream is False


class TestSeedreamResponseParsing:
    """Tests for provider response parsing."""

    @respx.mock
    async def test_single_url_response(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [{"url": "https://cdn.example.com/out.png", "index": 0}],
                    "usage": {"prompt_tokens": 10, "total_tokens": 20},
                },
                headers={"X-Request-Id": "req-1"},
            )
        )
        request = SeedreamService.build_request(model="test-model", prompt="cat")
        response, request_id = await service.generate(request)
        assert request_id == "req-1"
        assert response.created == 1721400000
        assert len(response.data) == 1
        assert response.data[0].url == "https://cdn.example.com/out.png"

    @respx.mock
    async def test_b64_json_response(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [{"b64_json": "aV9hbV9hbl9pbWFnZQ==", "index": 0}],
                },
            )
        )
        request = SeedreamService.build_request(model="test-model", prompt="cat")
        response, _ = await service.generate(request)
        assert response.data[0].b64_json == "aV9hbV9hbl9pbWFnZQ=="

    @respx.mock
    async def test_batch_response(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [
                        {"url": "https://cdn.example.com/1.png", "index": 0},
                        {"url": "https://cdn.example.com/2.png", "index": 1},
                        {"url": "https://cdn.example.com/3.png", "index": 2},
                    ],
                },
            )
        )
        request = SeedreamService.build_request(
            model="seedream-5-0-260128", prompt="batch", max_images=3
        )
        response, _ = await service.generate(request)
        assert len(response.data) == 3

    @respx.mock
    async def test_partial_failure_no_output(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [
                        {"url": "https://cdn.example.com/ok.png", "index": 0},
                        {"index": 1},  # no url or b64_json
                    ],
                },
            )
        )
        request = SeedreamService.build_request(
            model="seedream-5-0-260128", prompt="batch", max_images=2
        )
        response, _ = await service.generate(request)
        errors = SeedreamService.extract_item_errors(response)
        assert len(errors) == 1
        assert errors[0].index == 1
        assert errors[0].code == "NO_OUTPUT"

    @respx.mock
    async def test_usage_extraction(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [{"url": "https://cdn.example.com/img.png"}],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 30, "total_tokens": 45},
                },
            )
        )
        request = SeedreamService.build_request(model="test", prompt="cat")
        response, _ = await service.generate(request)
        usage = SeedreamService.extract_usage(response)
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 30
        assert usage.total_tokens == 45

    @respx.mock
    async def test_created_at_format(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "created": 1721400000,
                    "data": [{"url": "https://cdn.example.com/img.png"}],
                },
            )
        )
        request = SeedreamService.build_request(model="test", prompt="cat")
        response, _ = await service.generate(request)
        created = SeedreamService.get_created_at(response)
        assert "2024" in created or "2025" in created or "2026" in created


class TestSeedreamErrorPropagation:
    """Tests for error propagation through the Seedream adapter."""

    @respx.mock
    async def test_provider_error_raised(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "INVALID_PARAM", "message": "bad model"}},
            )
        )
        request = SeedreamService.build_request(model="bad", prompt="cat")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.http_status == 400
        assert exc_info.value.code == "INVALID_PARAM"

    @respx.mock
    async def test_timeout_raises_ambiguous(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            side_effect=httpx.TimeoutException("timed out")
        )
        request = SeedreamService.build_request(model="test", prompt="cat")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.code == "TIMEOUT"
        assert exc_info.value.ambiguous_completion is True

    @respx.mock
    async def test_connection_error_raises(self, service: SeedreamService) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            side_effect=httpx.ConnectError("refused")
        )
        request = SeedreamService.build_request(model="test", prompt="cat")
        with pytest.raises(ProviderError) as exc_info:
            await service.generate(request)
        assert exc_info.value.code == "CONNECTION_ERROR"
