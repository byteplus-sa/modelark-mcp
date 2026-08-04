"""ASGI-level HTTP health, origin, and authentication tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastmcp.server.auth import StaticTokenVerifier
from starlette.middleware import Middleware

from modelark_mcp.config.env import Settings
from modelark_mcp.security.http_middleware import RequestBodyLimitMiddleware
from modelark_mcp.server import create_server


def _jwt_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        MCP_TRANSPORT="http",
        MCP_HOST="127.0.0.1",
        MCP_AUTH_MODE="jwt",
        MCP_JWT_JWKS_URI="https://identity.example.com/.well-known/jwks.json",
        MCP_JWT_ISSUER="https://identity.example.com",
        MCP_JWT_AUDIENCE="modelark-mcp",
        MCP_ALLOWED_HOSTS="testserver",
        MCP_ALLOWED_ORIGINS="https://client.example.com",
        ARTIFACT_DIR=str(tmp_path / "artifacts"),
        BYTEPLUS_MODELARK_API_KEY="test-modelark-key",  # pragma: allowlist secret
    )


def _verifier() -> StaticTokenVerifier:
    return StaticTokenVerifier(
        tokens={
            "good-token": {
                "client_id": "test-client",
                "scopes": [
                    "seedream:generate",
                    "artifacts:read",
                ],
                "claims": {"sub": "alice", "tenant_id": "tenant-a"},
            },
            "read-only-token": {
                "client_id": "read-client",
                "scopes": ["artifacts:read"],
                "claims": {"sub": "reader", "tenant_id": "tenant-a"},
            },
        }
    )


@asynccontextmanager
async def _http_client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = _jwt_settings(tmp_path)
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[Middleware(RequestBodyLimitMiddleware, max_bytes=1024)],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        yield client


async def test_health_ready_and_metrics(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        health = await http_client.get("/health")
        ready = await http_client.get("/ready")
        metrics = await http_client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert metrics.status_code == 200
    assert "modelark_mcp_tool_requests_total" in metrics.text


async def test_mcp_rejects_missing_token(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Origin": "https://client.example.com",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
    assert response.status_code == 401


async def test_mcp_accepts_valid_token(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer good-token",
                "Origin": "https://client.example.com",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "ModelArk Seed Multimodal"


async def test_invalid_origin_is_rejected(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer good-token",
                "Origin": "https://evil.example.com",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert response.status_code in {403, 421}


async def test_component_scope_rejects_under_scoped_token(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer read-only-token",
                "Origin": "https://client.example.com",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "seedream_generate_image",
                    "arguments": {"input": {"prompt": "must not dispatch"}},
                },
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["isError"] is True
    assert "unknown tool" in payload["result"]["content"][0]["text"].lower()


async def test_oversized_body_is_rejected_before_mcp(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer good-token",
                "Origin": "https://client.example.com",
                "Accept": "application/json, text/event-stream",
            },
            content=b"x" * 1025,
        )
    assert response.status_code == 413


async def test_ready_without_provider_check(tmp_path: Path) -> None:
    async with _http_client(tmp_path) as http_client:
        ready = await http_client.get("/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert "providers" not in body


async def test_ready_with_provider_check_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modelark_mcp.providers.base import BaseHttpGateway

    async def _ok_health(self: BaseHttpGateway, *, timeout_seconds: float = 2.0) -> bool:
        return True

    monkeypatch.setattr(BaseHttpGateway, "health_check", _ok_health)

    settings = _jwt_settings(tmp_path)
    settings.readiness_check_providers = True
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[Middleware(RequestBodyLimitMiddleware, max_bytes=1024)],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        ready = await client.get("/ready")

    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert "providers" in body
    assert body["providers"]["modelark"] == "reachable"


async def test_ready_degraded_when_provider_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modelark_mcp.providers.base import BaseHttpGateway

    async def _down_health(self: BaseHttpGateway, *, timeout_seconds: float = 2.0) -> bool:
        return False

    monkeypatch.setattr(BaseHttpGateway, "health_check", _down_health)

    settings = _jwt_settings(tmp_path)
    settings.readiness_check_providers = True
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[Middleware(RequestBodyLimitMiddleware, max_bytes=1024)],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        ready = await client.get("/ready")

    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "degraded"
    assert body["providers"]["modelark"] == "unreachable"


async def test_rate_limit_allows_under_threshold(tmp_path: Path) -> None:
    from modelark_mcp.security.http_middleware import RateLimitMiddleware

    settings = _jwt_settings(tmp_path)
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[
            Middleware(RequestBodyLimitMiddleware, max_bytes=1024),
            Middleware(RateLimitMiddleware, rpm=10, burst=10),
        ],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        for _ in range(5):
            resp = await client.get("/health")
            assert resp.status_code == 200


async def test_rate_limit_blocks_over_threshold(tmp_path: Path) -> None:
    from modelark_mcp.security.http_middleware import RateLimitMiddleware

    settings = _jwt_settings(tmp_path)
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[
            Middleware(RequestBodyLimitMiddleware, max_bytes=1024),
            Middleware(RateLimitMiddleware, rpm=2, burst=2),
        ],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        r1 = await client.get("/health")
        r2 = await client.get("/health")
        r3 = await client.get("/health")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


async def test_rate_limit_retry_after_header(tmp_path: Path) -> None:
    from modelark_mcp.security.http_middleware import RateLimitMiddleware

    settings = _jwt_settings(tmp_path)
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[
            Middleware(RequestBodyLimitMiddleware, max_bytes=1024),
            Middleware(RateLimitMiddleware, rpm=1, burst=1),
        ],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        await client.get("/health")
        blocked = await client.get("/health")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}
    retry_after = int(blocked.headers["retry-after"])
    assert retry_after > 0


async def test_rate_limit_disabled_by_default(tmp_path: Path) -> None:
    settings = _jwt_settings(tmp_path)
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        middleware=[Middleware(RequestBodyLimitMiddleware, max_bytes=1024)],
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client,
    ):
        for _ in range(20):
            resp = await client.get("/health")
            assert resp.status_code == 200
