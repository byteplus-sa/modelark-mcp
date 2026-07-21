"""Shared test fixtures for integration tests.

Provides a fake MCP Context, a temp artifact store, and env var isolation
so tool handlers can be tested end-to-end without real credentials or network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from modelark_mcp.artifacts.filesystem_store import FilesystemArtifactStore


@dataclass
class FakeContext:
    """Minimal Context implementation for testing tool handlers."""

    messages: list[str] = field(default_factory=list)
    progress_reports: list[tuple[int, int]] = field(default_factory=list)

    async def info(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"INFO: {message}")

    async def debug(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"DEBUG: {message}")

    async def warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"WARNING: {message}")

    async def error(self, message: str, **kwargs: object) -> None:
        self.messages.append(f"ERROR: {message}")

    async def report_progress(self, progress: int, total: int) -> None:
        self.progress_reports.append((progress, total))

    async def read_resource(self, uri: str) -> object:
        raise NotImplementedError

    async def sample(self, messages: object, **kwargs: object) -> object:
        raise NotImplementedError


@pytest.fixture
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set test environment variables with fake credentials."""
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-modelark")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-test-speech")
    monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.test.example.com/api/v3")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.test.example.com")
    monkeypatch.setenv("SEEDREAM_DEFAULT_MODEL", "dola-seedream-5-0-pro-260628")
    monkeypatch.setenv("SEEDANCE_DEFAULT_MODEL", "dreamina-seedance-2-0-260128")
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / ".artifacts"))
    monkeypatch.setenv("ARTIFACT_BACKEND", "filesystem")

    # Clear cached settings and capability registry.
    from modelark_mcp.config.env import get_settings
    from modelark_mcp.config.model_capabilities import refresh_capability_registry

    get_settings.cache_clear()
    refresh_capability_registry()

    # Reset the artifact store singleton.
    import modelark_mcp.server as server_mod

    server_mod._artifact_store = None

    yield

    get_settings.cache_clear()
    refresh_capability_registry()
    server_mod._artifact_store = None


@pytest.fixture
def fake_ctx() -> FakeContext:
    return FakeContext()


@pytest.fixture
def temp_store(test_env: None, tmp_path: Path) -> FilesystemArtifactStore:
    """Return a temp filesystem artifact store."""
    return FilesystemArtifactStore(
        artifact_dir=str(tmp_path / ".artifacts"),
        ttl_seconds=3600,
    )
