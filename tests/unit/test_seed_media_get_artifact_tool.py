"""Unit tests for the ``seed_media_get_artifact`` tool handler.

Covers the Base64 round-trip with SHA-256 and byte count, the missing-artifact
error, and the cross-owner permission check.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from modelark_mcp.artifacts.filesystem_store import FilesystemArtifactStore
from modelark_mcp.security.auth_context import AuthContext
from modelark_mcp.tools.seed_media_get_artifact import (
    SeedMediaGetArtifactInput,
    SeedMediaGetArtifactOutput,
    seed_media_get_artifact,
)
from tests.fixtures.fake_context import FakeContext


@pytest.fixture
def store(tmp_path: Path) -> FilesystemArtifactStore:
    return FilesystemArtifactStore(artifact_dir=str(tmp_path), ttl_seconds=3600)


def _ctx_for(
    store: FilesystemArtifactStore,
    principal_id: str,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> FakeContext:
    monkeypatch.setattr(
        "modelark_mcp.tools.seed_media_get_artifact.get_runtime",
        lambda _ctx: SimpleNamespace(artifact_store=store),
    )
    monkeypatch.setattr(
        "modelark_mcp.tools.seed_media_get_artifact.get_principal",
        lambda _ctx: AuthContext(principal_id=principal_id, tenant_id=tenant_id),
    )
    return FakeContext()


class TestSeedMediaGetArtifact:
    async def test_returns_round_trip_base64_and_metadata(
        self,
        store: FilesystemArtifactStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        raw = b"\x00\x01fake audio payload\xff"
        ref = await store.put_base64(
            data=base64.b64encode(raw).decode(),
            media_type="audio",
            mime_type="audio/wav",
            auth=AuthContext(principal_id="alice", tenant_id="tenant-a"),
        )
        ctx = _ctx_for(store, "alice", "tenant-a", monkeypatch)

        result = await seed_media_get_artifact(
            SeedMediaGetArtifactInput(artifact_id=ref.id),
            ctx,
        )

        assert isinstance(result, SeedMediaGetArtifactOutput)
        assert result.artifact_id == ref.id
        assert result.media_type == "audio"
        assert result.mime_type == "audio/wav"
        assert result.bytes == len(raw)
        assert result.sha256 == hashlib.sha256(raw).hexdigest()
        assert base64.b64decode(result.data) == raw

    async def test_missing_artifact_raises_file_not_found(
        self,
        store: FilesystemArtifactStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        missing_id = str(uuid.uuid4())
        ctx = _ctx_for(store, "alice", "tenant-a", monkeypatch)

        with pytest.raises(FileNotFoundError):
            await seed_media_get_artifact(
                SeedMediaGetArtifactInput(artifact_id=missing_id),
                ctx,
            )

    async def test_cross_owner_fetch_raises_permission_error(
        self,
        store: FilesystemArtifactStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ref = await store.put_base64(
            data=base64.b64encode(b"owned by alice").decode(),
            media_type="image",
            mime_type="image/png",
            auth=AuthContext(principal_id="alice", tenant_id="tenant-a"),
        )
        ctx = _ctx_for(store, "bob", "tenant-a", monkeypatch)

        with pytest.raises(PermissionError):
            await seed_media_get_artifact(
                SeedMediaGetArtifactInput(artifact_id=ref.id),
                ctx,
            )

    async def test_cross_tenant_fetch_raises_permission_error(
        self,
        store: FilesystemArtifactStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ref = await store.put_base64(
            data=base64.b64encode(b"owned by tenant-a").decode(),
            media_type="video",
            mime_type="video/mp4",
            auth=AuthContext(principal_id="alice", tenant_id="tenant-a"),
        )
        ctx = _ctx_for(store, "alice", "tenant-b", monkeypatch)

        with pytest.raises(PermissionError):
            await seed_media_get_artifact(
                SeedMediaGetArtifactInput(artifact_id=ref.id),
                ctx,
            )
