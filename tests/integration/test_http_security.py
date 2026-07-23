"""ASGI-level HTTP health, origin, and authentication tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
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
