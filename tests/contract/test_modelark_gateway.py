"""Contract tests for the ModelArk gateway.

Covers exact request headers/body/path and response parsing against
redacted fixture shapes. Tests success, 4xx validation/moderation,
401/403 access, 429 quota, 5xx server errors, malformed JSON,
timeout, and connection error paths.

Uses ``respx`` to mock ``httpx.AsyncClient`` requests — no real network
calls are made.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from modelark_mcp.providers.modelark.client import ModelArkGateway

MODELARK_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"


@pytest.fixture
def gateway() -> ModelArkGateway:
    """Create a ModelArk gateway with test credentials."""
    return ModelArkGateway(
        api_key="sk-test-key",  # pragma: allowlist secret
        base_url=MODELARK_BASE,
        timeout=10.0,
        connect_timeout=5.0,
    )


class TestModelArkGatewaySuccess:
    """Tests for successful ModelArk API calls."""

    @respx.mock
    async def test_post_success(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                200,
                json={"created": 1721400000, "data": [{"url": "https://cdn.example.com/img.png"}]},
                headers={"X-Request-Id": "req-123"},
            )
        )
        response = await gateway.post("/images/generations", {"model": "test", "prompt": "cat"})
        assert response.status_code == 200
        assert response.json()["data"][0]["url"] == "https://cdn.example.com/img.png"

    @respx.mock
    async def test_get_success(self, gateway: ModelArkGateway) -> None:
        respx.get(f"{MODELARK_BASE}/contents/generations/tasks/task-1").mock(
            return_value=httpx.Response(
                200,
                json={"id": "task-1", "model": "test", "status": "queued"},
                headers={"X-Request-Id": "req-456"},
            )
        )
        response = await gateway.get("/contents/generations/tasks/task-1")
        assert response.status_code == 200
        assert response.json()["id"] == "task-1"

    @respx.mock
    async def test_delete_success(self, gateway: ModelArkGateway) -> None:
        respx.delete(f"{MODELARK_BASE}/contents/generations/tasks/task-1").mock(
            return_value=httpx.Response(
                204,
                headers={"X-Request-Id": "req-789"},
            )
        )
        response = await gateway.delete("/contents/generations/tasks/task-1")
        assert response.status_code == 204

    @respx.mock
    async def test_authorization_header_set(self, gateway: ModelArkGateway) -> None:
        route = respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(200, json={})
        )
        await gateway.post("/images/generations", {})
        assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test-key"

    @respx.mock
    async def test_content_type_header_set(self, gateway: ModelArkGateway) -> None:
        route = respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(200, json={})
        )
        await gateway.post("/images/generations", {})
        assert route.calls.last.request.headers["Content-Type"] == "application/json"

    @respx.mock
    async def test_extract_request_id(self, gateway: ModelArkGateway) -> None:
        response = httpx.Response(200, json={}, headers={"X-Request-Id": "req-abc"})
        assert ModelArkGateway.extract_request_id(response) == "req-abc"

    @respx.mock
    async def test_extract_request_id_lowercase(self, gateway: ModelArkGateway) -> None:
        response = httpx.Response(200, json={}, headers={"x-request-id": "req-xyz"})
        assert ModelArkGateway.extract_request_id(response) == "req-xyz"

    @respx.mock
    async def test_extract_request_id_missing(self, gateway: ModelArkGateway) -> None:
        response = httpx.Response(200, json={})
        assert ModelArkGateway.extract_request_id(response) is None

    async def test_close(self, gateway: ModelArkGateway) -> None:
        await gateway._ensure_client()
        assert gateway._client is not None
        await gateway.close()
        assert gateway._client is None


class TestModelArkGatewayErrors:
    """Tests for ModelArk error normalization."""

    @respx.mock
    async def test_400_validation_error(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": "INVALID_PARAM", "message": "model is required"}},
                headers={"X-Request-Id": "req-400"},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.provider == "modelark"
        assert error.http_status == 400
        assert error.code == "INVALID_PARAM"
        assert "model is required" in error.message
        assert error.request_id == "req-400"
        assert not error.retryable

    @respx.mock
    async def test_401_access_error(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                401,
                json={"error": {"code": "UNAUTHORIZED", "message": "invalid API key"}},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 401
        assert error.code == "UNAUTHORIZED"
        assert not error.retryable

    @respx.mock
    async def test_403_forbidden_error(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                403,
                json={"error": {"code": "FORBIDDEN", "message": "model not activated"}},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 403
        assert not error.retryable

    @respx.mock
    async def test_429_rate_limit_error(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                429,
                json={"error": {"code": "RATE_LIMITED", "message": "too many requests"}},
                headers={"Retry-After": "60"},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 429
        assert error.retryable

    @respx.mock
    async def test_500_server_error(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                500,
                json={"error": {"code": "INTERNAL", "message": "internal server error"}},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 500
        assert error.retryable

    @respx.mock
    async def test_503_service_unavailable(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                503,
                json={"error": {"code": "UNAVAILABLE", "message": "service unavailable"}},
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 503
        assert error.retryable

    @respx.mock
    async def test_malformed_json_body(self, gateway: ModelArkGateway) -> None:
        respx.post(f"{MODELARK_BASE}/images/generations").mock(
            return_value=httpx.Response(
                500,
                content=b"not json at all",
            )
        )
        response = await gateway.post("/images/generations", {})
        error = ModelArkGateway.normalize_error(response, "generate_image")
        assert error.http_status == 500
        assert "not json at all" in error.message
        assert error.retryable

    def test_normalize_timeout(self) -> None:
        error = ModelArkGateway.normalize_timeout("generate_image")
        assert error.code == "TIMEOUT"
        assert error.ambiguous_completion is True
        assert not error.retryable
        assert "generate_image" in error.message
        assert "may have succeeded" in error.message

    def test_normalize_connection_error(self) -> None:
        exc = httpx.ConnectError("connection refused")
        error = ModelArkGateway.normalize_connection_error("generate_image", exc)
        assert error.code == "CONNECTION_ERROR"
        assert error.retryable
        assert "connection refused" in error.message
