"""Global pytest fixtures that keep the suite deterministic and offline."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

_SETTINGS_ENV_PREFIXES = (
    "BYTEPLUS_",
    "MCP_",
    "FASTMCP_",
    "LAS_",
    "SEEDREAM_",
    "SEEDANCE_",
    "TOS_",
    "S3_",
    "OBJECT_STORAGE_",
    "SEED_SPEECH_",
    "ARTIFACT_",
    "PROVIDER_",
    "PRINCIPAL_",
    "DAILY_",
    "MODELARK_",
)


@pytest.fixture(autouse=True)
def isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear leaked Settings env vars so ``Settings(_env_file=None)`` sees clean defaults.

    The developer's real ``.env`` may be present in the shell environment.
    pydantic-settings reads ``os.environ`` even when ``_env_file=None``, so
    without this isolation unit tests that assert default values would read
    real credentials and fail non-deterministically. Tests that need a value
    set it via ``monkeypatch.setenv`` after this fixture runs.
    """
    for key in list(os.environ):
        if key.startswith(_SETTINGS_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    from modelark_mcp.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
