"""Unit tests for filesystem artifact store."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest

from modelark_mcp.artifacts.filesystem_store import FilesystemArtifactStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> FilesystemArtifactStore:
    """Create a filesystem artifact store in a temp directory."""
    return FilesystemArtifactStore(artifact_dir=str(tmp_path), ttl_seconds=3600)


class TestFilesystemArtifactStore:
    """Tests for the filesystem artifact store."""

    async def test_put_base64_and_get(self, store: FilesystemArtifactStore) -> None:
        raw = b"fake audio data"
        data = base64.b64encode(raw).decode()
        ref = await store.put_base64(data=data, media_type="audio", mime_type="audio/wav")
        assert ref.id
        assert ref.uri == f"seed-media://artifacts/{ref.id}"
        assert ref.media_type == "audio"
        assert ref.mime_type == "audio/wav"
        assert ref.bytes == len(raw)
        assert ref.sha256

        artifact = await store.get(ref.id)
        assert artifact.data == raw
        assert artifact.media_type == "audio"
        assert artifact.mime_type == "audio/wav"

    async def test_put_base64_computes_sha256(self, store: FilesystemArtifactStore) -> None:
        import hashlib

        raw = b"test data for sha256"
        data = base64.b64encode(raw).decode()
        ref = await store.put_base64(data=data, media_type="image", mime_type="image/png")
        expected = hashlib.sha256(raw).hexdigest()
        assert ref.sha256 == expected

    async def test_get_nonexistent_raises(self, store: FilesystemArtifactStore) -> None:
        with pytest.raises(FileNotFoundError):
            await store.get("nonexistent-id")

    async def test_delete_expired_returns_zero(self, store: FilesystemArtifactStore) -> None:
        from datetime import UTC, datetime

        count = await store.delete_expired(now=datetime.now(UTC))
        assert count == 0

    async def test_delete_expired_removes_artifacts(self, store: FilesystemArtifactStore) -> None:
        from datetime import UTC, datetime, timedelta

        raw = b"expired data"
        data = base64.b64encode(raw).decode()
        ref = await store.put_base64(data=data, media_type="video", mime_type="video/mp4")

        # Verify it exists.
        artifact = await store.get(ref.id)
        assert artifact.data == raw

        # Delete expired with a future timestamp to trigger deletion.
        future = datetime.now(UTC) + timedelta(days=1)
        count = await store.delete_expired(now=future)
        assert count == 1

        # Verify it's gone.
        with pytest.raises(FileNotFoundError):
            await store.get(ref.id)
