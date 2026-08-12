"""Tests for process-lifetime ownership, budgets, and concurrency controls."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastmcp.server.auth import AccessToken

from modelark_mcp.config.env import Settings
from modelark_mcp.domain.artifacts import ArtifactRef, MediaType
from modelark_mcp.runtime import (
    BudgetExceededError,
    BudgetLedger,
    CostEstimate,
    ProviderLimiters,
    SQLiteTaskArtifactCache,
    SQLiteTaskOwnershipStore,
    close_runtime_services,
    create_runtime_services,
    get_principal,
)
from modelark_mcp.security.auth_context import AuthContext
from tests.fixtures.fake_context import FakeContext


def _make_ref(ref_id: str = "art-1") -> ArtifactRef:
    return ArtifactRef(
        id=ref_id,
        uri=f"seed-media://artifacts/{ref_id}",
        media_type=MediaType.VIDEO,
        mime_type="video/mp4",
        bytes=100,
        sha256="abc123",
        created_at=datetime.now(UTC).isoformat(),
    )


async def test_task_artifact_cache_set_and_get(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3")
    ref = _make_ref("art-get")
    await cache.set("modelark", "task-1", {"video": ref, "last_frame": None})
    result = await cache.get("modelark", "task-1")
    assert result is not None
    assert result["video"] is not None
    assert result["video"].id == "art-get"
    assert result["last_frame"] is None
    await cache.close()


async def test_task_artifact_cache_returns_none_for_missing(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3")
    assert await cache.get("modelark", "nope") is None
    await cache.close()


async def test_task_artifact_cache_upsert(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3")
    ref1 = _make_ref("art-old")
    ref2 = _make_ref("art-new")
    await cache.set("modelark", "task-up", {"video": ref1, "last_frame": None})
    await cache.set("modelark", "task-up", {"video": ref2, "last_frame": None})
    result = await cache.get("modelark", "task-up")
    assert result is not None
    assert result["video"] is not None
    assert result["video"].id == "art-new"
    await cache.close()


async def test_task_artifact_cache_pop(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3")
    ref = _make_ref("art-pop")
    await cache.set("modelark", "task-pop", {"video": ref, "last_frame": None})
    popped = await cache.pop("modelark", "task-pop")
    assert popped is not None
    assert popped["video"] is not None
    assert popped["video"].id == "art-pop"
    assert await cache.get("modelark", "task-pop") is None
    await cache.close()


async def test_task_artifact_cache_clear(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3")
    await cache.set("modelark", "task-a", {"video": _make_ref("a"), "last_frame": None})
    await cache.set("modelark", "task-b", {"video": _make_ref("b"), "last_frame": None})
    await cache.clear()
    assert await cache.get("modelark", "task-a") is None
    assert await cache.get("modelark", "task-b") is None
    await cache.close()


async def test_task_artifact_cache_ttl_expiry(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3", ttl_seconds=1)
    await cache.set("modelark", "task-ttl", {"video": _make_ref("ttl"), "last_frame": None})

    fake_old = datetime.now(UTC) - timedelta(seconds=2)
    cache._connection.execute(
        "UPDATE task_artifacts SET created_at = ? WHERE task_id = ?",
        (fake_old.isoformat(), "task-ttl"),
    )
    cache._connection.commit()

    assert await cache.get("modelark", "task-ttl") is None
    await cache.close()


async def test_task_artifact_cache_max_size_eviction(tmp_path: Path) -> None:
    cache = SQLiteTaskArtifactCache(tmp_path / "runtime.sqlite3", max_size=2)
    await cache.set("modelark", "task-1", {"video": _make_ref("r1"), "last_frame": None})
    await asyncio.sleep(0.01)
    await cache.set("modelark", "task-2", {"video": _make_ref("r2"), "last_frame": None})
    await asyncio.sleep(0.01)
    await cache.set("modelark", "task-3", {"video": _make_ref("r3"), "last_frame": None})

    assert await cache.get("modelark", "task-1") is None
    assert await cache.get("modelark", "task-2") is not None
    assert await cache.get("modelark", "task-3") is not None
    await cache.close()


async def test_task_artifact_cache_survives_reopen(tmp_path: Path) -> None:
    db = tmp_path / "runtime.sqlite3"
    cache1 = SQLiteTaskArtifactCache(db)
    await cache1.set(
        "modelark", "task-survive", {"video": _make_ref("survive"), "last_frame": None}
    )
    await cache1.close()

    cache2 = SQLiteTaskArtifactCache(db)
    result = await cache2.get("modelark", "task-survive")
    assert result is not None
    assert result["video"] is not None
    assert result["video"].id == "survive"
    await cache2.close()


async def test_task_ownership_is_principal_and_tenant_scoped(tmp_path: Path) -> None:
    store = SQLiteTaskOwnershipStore(tmp_path / "runtime.sqlite3")
    alice = AuthContext(principal_id="alice", tenant_id="tenant-a")
    await store.record("modelark", "task-1", alice)

    await store.require_owner("modelark", "task-1", alice)
    assert await store.list_task_ids("modelark", alice) == {"task-1"}

    with pytest.raises(PermissionError):
        await store.require_owner(
            "modelark", "task-1", AuthContext(principal_id="bob", tenant_id="tenant-a")
        )
    with pytest.raises(PermissionError):
        await store.require_owner(
            "modelark", "task-1", AuthContext(principal_id="alice", tenant_id="tenant-b")
        )
    await store.close()


async def test_task_ownership_and_artifacts_are_provider_scoped(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    store = SQLiteTaskOwnershipStore(database)
    cache = SQLiteTaskArtifactCache(database)
    alice = AuthContext(principal_id="alice", tenant_id="tenant-a")
    bob = AuthContext(principal_id="bob", tenant_id="tenant-a")

    await store.record("modelark", "shared-id", alice)
    await store.record("vod-mediakit", "shared-id", bob)
    await cache.set("modelark", "shared-id", {"video": _make_ref("modelark"), "last_frame": None})
    await cache.set(
        "vod-mediakit", "shared-id", {"video": _make_ref("mediakit"), "last_frame": None}
    )

    await store.require_owner("modelark", "shared-id", alice)
    await store.require_owner("vod-mediakit", "shared-id", bob)
    assert await store.list_task_ids("modelark", alice) == {"shared-id"}
    assert await store.list_task_ids("vod-mediakit", alice) == set()
    modelark = await cache.get("modelark", "shared-id")
    mediakit = await cache.get("vod-mediakit", "shared-id")
    assert modelark is not None and modelark["video"] is not None
    assert mediakit is not None and mediakit["video"] is not None
    assert modelark["video"].id == "modelark"
    assert mediakit["video"].id == "mediakit"
    await cache.close()
    await store.close()


async def test_legacy_runtime_tables_migrate_to_modelark_provider(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE task_ownership (
            task_id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE task_artifacts (
            task_id TEXT PRIMARY KEY,
            artifacts_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    created_at = datetime.now(UTC).isoformat()
    connection.execute(
        "INSERT INTO task_ownership VALUES (?, ?, ?, ?)",
        ("legacy-task", "alice", "tenant-a", created_at),
    )
    connection.execute(
        "INSERT INTO task_artifacts VALUES (?, ?, ?)",
        (
            "legacy-task",
            json.dumps({"video": _make_ref("legacy").model_dump(mode="json"), "last_frame": None}),
            created_at,
        ),
    )
    connection.commit()
    connection.close()

    store = SQLiteTaskOwnershipStore(database)
    cache = SQLiteTaskArtifactCache(database)
    owner = AuthContext(principal_id="alice", tenant_id="tenant-a")
    await store.require_owner("modelark", "legacy-task", owner)
    assert await store.list_task_ids("modelark", owner) == {"legacy-task"}
    migrated = await cache.get("modelark", "legacy-task")
    assert migrated is not None and migrated["video"] is not None
    assert migrated["video"].id == "legacy"
    assert await cache.get("vod-mediakit", "legacy-task") is None
    await cache.close()
    await store.close()


async def test_runtime_migration_recovers_stranded_legacy_tables(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE task_ownership_legacy (
            task_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL, created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE task_artifacts_legacy (
            task_id TEXT PRIMARY KEY, artifacts_json TEXT NOT NULL, created_at TEXT NOT NULL
        )
        """
    )
    created_at = datetime.now(UTC).isoformat()
    connection.execute(
        "INSERT INTO task_ownership_legacy VALUES (?, ?, ?, ?)",
        ("stranded", "alice", "tenant-a", created_at),
    )
    connection.execute(
        "INSERT INTO task_artifacts_legacy VALUES (?, ?, ?)",
        (
            "stranded",
            json.dumps(
                {"video": _make_ref("stranded-ref").model_dump(mode="json"), "last_frame": None}
            ),
            created_at,
        ),
    )
    connection.commit()
    connection.close()

    store = SQLiteTaskOwnershipStore(database)
    cache = SQLiteTaskArtifactCache(database)
    owner = AuthContext(principal_id="alice", tenant_id="tenant-a")
    await store.require_owner("modelark", "stranded", owner)
    recovered = await cache.get("modelark", "stranded")
    assert recovered is not None and recovered["video"] is not None
    assert recovered["video"].id == "stranded-ref"
    await cache.close()
    await store.close()


async def test_budget_reservations_block_and_release(tmp_path: Path) -> None:
    ledger = BudgetLedger(tmp_path / "runtime.sqlite3", daily_limit_usd=0.10)
    owner = AuthContext(principal_id="alice", tenant_id="tenant-a")
    first = await ledger.reserve(owner, CostEstimate(product="image", amount_usd=0.08))

    with pytest.raises(BudgetExceededError):
        await ledger.reserve(owner, CostEstimate(product="image", amount_usd=0.03))

    await ledger.release(first)
    second = await ledger.reserve(owner, CostEstimate(product="image", amount_usd=0.03))
    await ledger.commit(second)
    await ledger.close()


async def test_provider_limit_is_shared_across_principals() -> None:
    limiters = ProviderLimiters(provider_limit=2, principal_limit=2)
    active = 0
    maximum = 0
    gate = asyncio.Event()

    async def worker(index: int) -> None:
        nonlocal active, maximum
        owner = AuthContext(principal_id=f"p-{index}", tenant_id="tenant")
        async with limiters.acquire("modelark", owner):
            active += 1
            maximum = max(maximum, active)
            await gate.wait()
            active -= 1

    tasks = [asyncio.create_task(worker(index)) for index in range(4)]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert maximum == 2
    gate.set()
    await asyncio.gather(*tasks)


async def test_principal_limit_is_shared_across_providers() -> None:
    limiters = ProviderLimiters(provider_limit=5, principal_limit=1)
    owner = AuthContext(principal_id="alice", tenant_id="tenant")
    active = 0
    maximum = 0

    async def worker(provider: str) -> None:
        nonlocal active, maximum
        async with limiters.acquire(provider, owner):  # type: ignore[arg-type]
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            active -= 1

    await asyncio.gather(worker("modelark"), worker("seed-speech"))
    assert maximum == 1


async def test_http_principal_comes_from_verified_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        MCP_TRANSPORT="http",
        MCP_AUTH_MODE="jwt",
        MCP_JWT_JWKS_URI="https://identity.example.com/jwks.json",
        MCP_JWT_ISSUER="https://identity.example.com",
        MCP_JWT_AUDIENCE="modelark-mcp",
        ARTIFACT_DIR=str(tmp_path / "artifacts"),
    )
    runtime = await create_runtime_services(settings)
    monkeypatch.setattr(
        "modelark_mcp.runtime.get_access_token",
        lambda: AccessToken(
            token="redacted",
            client_id="client-a",
            scopes=["seedream:generate"],
            claims={"sub": "alice", "tenant_id": "tenant-a"},
        ),
    )
    try:
        principal = get_principal(FakeContext(lifespan_context={"runtime": runtime}))
    finally:
        await close_runtime_services(runtime)

    assert principal.principal_id == "alice"
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"seedream:generate"})
    assert principal.transport == "http"
