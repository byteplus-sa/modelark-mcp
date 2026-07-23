"""Global pytest fixtures that keep the suite deterministic and offline."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def deterministic_public_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Resolve test hostnames without consulting external DNS."""
    monkeypatch.setattr(
        "modelark_mcp.security.url_policy.system_resolver",
        lambda _hostname, _port: ("93.184.216.34",),
    )
    yield


@pytest.fixture(autouse=True)
def block_external_sockets(socket_disabled: None) -> Iterator[None]:
    """Fail every test that attempts real network I/O."""
    yield
