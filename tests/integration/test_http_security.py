"""ASGI-level HTTP health, origin, and authentication tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp.server.auth import StaticTokenVerifier
from starlette.middleware import Middleware

from modelark_mcp.config.env import Settings
from modelark_mcp.security.http_middleware import (
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
)
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
        BYTEPLUS_VOD_MEDIAKIT_API_KEY="test-mediakit-key",  # pragma: allowlist secret
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
            "vod-token": {
                "client_id": "vod-client",
                "scopes": ["vod:enhance"],
                "claims": {"sub": "video-user", "tenant_id": "tenant-a"},
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


async def test_vod_scope_rejects_under_scoped_token(tmp_path: Path) -> None:
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
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "vod_enhance_video",
                    "arguments": {
                        "input": {"video_url": "https://example.com/input.mp4", "persist": False}
                    },
                },
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["isError"] is True
    assert "unknown tool" in payload["result"]["content"][0]["text"].lower()


async def test_vod_scope_allows_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from modelark_mcp.providers.vod_mediakit.enhancement import VodMediaKitEnhancementService
    from modelark_mcp.providers.vod_mediakit.schemas import EnhancementSubmission
    from modelark_mcp.security.auth_context import AuthContext

    async def enhance(
        _self: VodMediaKitEnhancementService, _request: object
    ) -> EnhancementSubmission:
        return EnhancementSubmission(
            status="succeeded", output_url="https://output.example.com/enhanced.mp4"
        )

    async def close(_self: VodMediaKitEnhancementService) -> None:
        return None

    monkeypatch.setattr(VodMediaKitEnhancementService, "enhance", enhance)
    monkeypatch.setattr(VodMediaKitEnhancementService, "close", close)
    monkeypatch.setattr(
        "modelark_mcp.tools.vod_enhance_video.get_principal",
        lambda _ctx: AuthContext(principal_id="video-user", tenant_id="tenant-a"),
    )
    async with _http_client(tmp_path) as http_client:
        response = await http_client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer vod-token",
                "Origin": "https://client.example.com",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "vod_enhance_video",
                    "arguments": {
                        "input": {"video_url": "https://example.com/input.mp4", "persist": False}
                    },
                },
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["isError"] is False
    assert payload["result"]["structuredContent"]["provider"] == "byteplus-vod-mediakit"


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


class TestRateLimitMiddlewareBucketing:
    """The proxy-aware client key groups by forwarded-for or client IP."""

    @staticmethod
    def _scope(client_ip: str, forwarded_for: str | None = None) -> dict[str, object]:
        headers = [] if forwarded_for is None else [(b"x-forwarded-for", forwarded_for.encode())]
        return {"type": "http", "client": (client_ip, 1234), "headers": headers}

    def test_trust_proxy_headers_uses_first_forwarded_for(self) -> None:
        middleware = RateLimitMiddleware(None, rpm=10, trust_proxy_headers=True)  # type: ignore[arg-type]
        assert middleware._client_key(self._scope("10.0.0.5", "1.2.3.4, 5.6.7.8")) == "1.2.3.4"

    def test_trust_proxy_headers_groups_same_forwarded_for(self) -> None:
        middleware = RateLimitMiddleware(None, rpm=10, trust_proxy_headers=True)  # type: ignore[arg-type]
        first = middleware._client_key(self._scope("10.0.0.5", "1.2.3.4, 9.9.9.9"))
        second = middleware._client_key(self._scope("10.0.0.6", "1.2.3.4"))
        assert first == second == "1.2.3.4"

    def test_trust_proxy_headers_off_uses_client_ip(self) -> None:
        middleware = RateLimitMiddleware(None, rpm=10)  # type: ignore[arg-type]
        assert middleware._client_key(self._scope("10.0.0.5", "1.2.3.4")) == "10.0.0.5"

    def test_distinct_client_ips_are_not_grouped(self) -> None:
        middleware = RateLimitMiddleware(None, rpm=10)  # type: ignore[arg-type]
        assert middleware._client_key(self._scope("10.0.0.1")) != middleware._client_key(
            self._scope("10.0.0.2")
        )

    async def test_bucket_count_stays_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = [0.0]
        monkeypatch.setattr(
            "modelark_mcp.security.http_middleware.time.monotonic", lambda: clock[0]
        )
        middleware = RateLimitMiddleware(None, rpm=60000, burst=60000)  # type: ignore[arg-type]
        for index in range(middleware._MAX_BUCKETS + 100):
            await middleware._consume(f"ip-{index}")
        assert len(middleware._buckets) > middleware._MAX_BUCKETS

        clock[0] = 10_000_000
        await middleware._consume("ip-final")
        assert len(middleware._buckets) <= middleware._MAX_BUCKETS


async def test_create_server_applies_body_and_rate_limit_middleware(tmp_path: Path) -> None:
    settings = _jwt_settings(tmp_path)
    settings.rate_limit_rpm = 10
    settings.rate_limit_burst = 10
    settings.rate_limit_trust_proxy_headers = True
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )

    stack: list[tuple[str, object]] = []
    node: object = app.build_middleware_stack()
    while node is not None:
        stack.append((type(node).__name__, node))
        node = getattr(node, "app", None)

    names = [name for name, _ in stack]
    assert "RequestBodyLimitMiddleware" in names
    assert "RateLimitMiddleware" in names
    assert names.index("RequestBodyLimitMiddleware") < names.index("RateLimitMiddleware")
    rate_limit_node = next(node for name, node in stack if name == "RateLimitMiddleware")
    assert rate_limit_node.trust_proxy_headers is True


async def test_ready_probes_use_resolved_settings_urls(tmp_path: Path) -> None:
    settings = _jwt_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "modelark_api_key": "test-modelark-key",
            "vod_mediakit_api_key": "",
            "seed_speech_api_key": "",
            "modelark_base_url": "https://override.example.com",
        }
    )
    settings.readiness_check_providers = True
    server = create_server(settings, auth_provider=_verifier())
    app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )

    with respx.mock:
        probe_route = respx.get("https://override.example.com/").mock(
            return_value=httpx.Response(200)
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client,
        ):
            ready = await client.get("/ready")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "providers": {"modelark": "reachable"}}
    assert probe_route.called
