"""Entrypoint dispatch tests for ``python -m modelark_mcp``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import modelark_mcp.__main__ as entrypoint


def test_main_runs_stdio_transport(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr(entrypoint, "get_settings", lambda: SimpleNamespace(mcp_transport="stdio"))
    monkeypatch.setattr(entrypoint.mcp, "run", run)

    entrypoint.main()

    run.assert_called_once_with(transport="stdio")


def test_main_configures_protected_http(monkeypatch) -> None:
    run = Mock()
    settings = SimpleNamespace(
        mcp_transport="http",
        mcp_host="127.0.0.1",
        mcp_port=3100,
        allowed_hosts=["127.0.0.1"],
        allowed_origins=["https://client.example.com"],
        request_timeout_ms=600_000,
    )
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint.mcp, "run", run)

    entrypoint.main()

    kwargs = run.call_args.kwargs
    assert kwargs["transport"] == "http"
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 3100
    assert kwargs["host_origin_protection"] is True
    assert kwargs["allowed_hosts"] == ["127.0.0.1"]
    assert kwargs["allowed_origins"] == ["https://client.example.com"]
    assert kwargs["stateless_http"] is True
    assert kwargs["uvicorn_config"] == {"timeout_graceful_shutdown": 600}
    assert "middleware" not in kwargs


def test_main_wires_rate_limiter_when_enabled(monkeypatch) -> None:
    run = Mock()
    settings = SimpleNamespace(
        mcp_transport="http",
        mcp_host="127.0.0.1",
        mcp_port=3100,
        allowed_hosts=["127.0.0.1"],
        allowed_origins=["https://client.example.com"],
        request_timeout_ms=600_000,
    )
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint.mcp, "run", run)

    entrypoint.main()

    kwargs = run.call_args.kwargs
    assert kwargs["transport"] == "http"
    assert kwargs["stateless_http"] is True
    assert "middleware" not in kwargs
