"""Tests for process-lifetime ownership, budgets, and concurrency controls."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastmcp.server.auth import AccessToken

from modelark_mcp.config.env import Settings
from modelark_mcp.runtime import (
    BudgetExceededError,
    BudgetLedger,
    CostEstimate,
    ProviderLimiters,
    SQLiteTaskOwnershipStore,
    close_runtime_services,
    create_runtime_services,
    get_principal,
)
from modelark_mcp.security.auth_context import AuthContext
from tests.fixtures.fake_context import FakeContext


async def test_task_ownership_is_principal_and_tenant_scoped(tmp_path: Path) -> None:
    store = SQLiteTaskOwnershipStore(tmp_path / "runtime.sqlite3")
    alice = AuthContext(principal_id="alice", tenant_id="tenant-a")
    await store.record("task-1", alice)

    await store.require_owner("task-1", alice)
    assert await store.list_task_ids(alice) == {"task-1"}

    with pytest.raises(PermissionError):
        await store.require_owner("task-1", AuthContext(principal_id="bob", tenant_id="tenant-a"))
    with pytest.raises(PermissionError):
        await store.require_owner("task-1", AuthContext(principal_id="alice", tenant_id="tenant-b"))
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
