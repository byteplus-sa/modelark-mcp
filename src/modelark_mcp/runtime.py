"""Process-lifetime services shared by tools and resources.

The FastMCP lifespan owns this container. Keeping artifact persistence,
concurrency controls, ownership, and budget state here prevents request-scoped
limiters and mutable server-module globals from leaking across test servers.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from cachetools import TTLCache
from fastmcp.server.dependencies import get_access_token

from modelark_mcp.artifacts.filesystem_store import FilesystemArtifactStore
from modelark_mcp.artifacts.object_storage_store import ObjectStorageArtifactStore
from modelark_mcp.config.env import Settings
from modelark_mcp.domain.artifacts import ArtifactRef
from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.observability.logger import info as log_info
from modelark_mcp.observability.logger import warning as log_warning
from modelark_mcp.observability.metrics import BUDGET_REJECTIONS
from modelark_mcp.security.auth_context import AuthContext, PrincipalContext
from modelark_mcp.security.safe_downloader import SafeDownloader

if TYPE_CHECKING:
    from fastmcp import Context, FastMCP

    from modelark_mcp.artifacts.store import ArtifactStore

ProviderKey = Literal["modelark", "seed-speech", "vod-mediakit", "tos", "s3"]


class ProviderLimiters:
    """Shared provider and bounded per-principal concurrency controls."""

    def __init__(
        self,
        *,
        provider_limit: int = 5,
        principal_limit: int = 3,
        principal_cache_size: int = 10_000,
        principal_ttl_seconds: int = 86_400,
    ) -> None:
        if provider_limit <= 0 or principal_limit <= 0:
            raise ValueError("Concurrency limits must be positive.")
        self._provider = {
            "modelark": asyncio.Semaphore(provider_limit),
            "seed-speech": asyncio.Semaphore(provider_limit),
            "vod-mediakit": asyncio.Semaphore(provider_limit),
            "tos": asyncio.Semaphore(provider_limit),
            "s3": asyncio.Semaphore(provider_limit),
        }
        self._principal_limit = principal_limit
        self._principals: TTLCache[str, asyncio.Semaphore] = TTLCache(
            maxsize=principal_cache_size,
            ttl=principal_ttl_seconds,
        )
        self._cache_lock = asyncio.Lock()

    def provider(self, provider: ProviderKey) -> asyncio.Semaphore:
        return self._provider[provider]

    async def principal(self, owner: AuthContext) -> asyncio.Semaphore:
        key = f"{owner.tenant_id}\0{owner.principal_id}"
        async with self._cache_lock:
            limiter = self._principals.get(key)
            if limiter is None:
                limiter = asyncio.Semaphore(self._principal_limit)
                self._principals[key] = limiter
            return limiter

    @asynccontextmanager
    async def acquire(
        self,
        provider: ProviderKey,
        owner: AuthContext,
    ) -> AsyncIterator[None]:
        principal_limiter = await self.principal(owner)
        async with self.provider(provider), principal_limiter:
            yield


class TaskOwnershipStore(Protocol):
    async def record(self, provider: str, task_id: str, owner: AuthContext) -> None: ...

    async def require_owner(self, provider: str, task_id: str, owner: AuthContext) -> None: ...

    async def list_task_ids(self, provider: str, owner: AuthContext) -> set[str]: ...

    async def prune(self, max_age_days: int) -> int: ...

    async def ping(self) -> None: ...

    async def close(self) -> None: ...


class TaskArtifactCache(Protocol):
    async def get(self, provider: str, task_id: str) -> dict[str, ArtifactRef | None] | None: ...

    async def set(
        self,
        provider: str,
        task_id: str,
        artifacts: dict[str, ArtifactRef | None],
    ) -> None: ...

    async def pop(self, provider: str, task_id: str) -> dict[str, ArtifactRef | None] | None: ...

    async def prune_expired(self) -> int: ...

    async def clear(self) -> None: ...

    async def close(self) -> None: ...


class SQLiteTaskOwnershipStore:
    """Small single-instance ownership database for provider task IDs."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._ensure_schema()
        self._connection.commit()
        self._lock = asyncio.Lock()

    def _ensure_schema(self) -> None:
        """Create or migrate the ownership table to provider-scoped keys."""
        with self._connection:
            columns = {
                str(row[1])
                for row in self._connection.execute("PRAGMA table_info(task_ownership)").fetchall()
            }
            legacy_exists = self._table_exists("task_ownership_legacy")
            if columns and "provider" not in columns:
                if legacy_exists:
                    self._connection.execute(
                        """
                        INSERT OR REPLACE INTO task_ownership_legacy
                        SELECT task_id, principal_id, tenant_id, created_at FROM task_ownership
                        """
                    )
                    self._connection.execute("DROP TABLE task_ownership")
                else:
                    self._connection.execute(
                        "ALTER TABLE task_ownership RENAME TO task_ownership_legacy"
                    )
                legacy_exists = True
            self._create_table()
            if legacy_exists:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO task_ownership(
                        provider, task_id, principal_id, tenant_id, created_at
                    )
                    SELECT 'modelark', task_id, principal_id, tenant_id, created_at
                    FROM task_ownership_legacy
                    """
                )
                self._connection.execute("DROP TABLE task_ownership_legacy")

    def _table_exists(self, table: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )

    def _create_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_ownership (
                provider TEXT NOT NULL,
                task_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(provider, task_id)
            )
            """
        )

    async def record(self, provider: str, task_id: str, owner: AuthContext) -> None:
        async with self._lock:
            self._connection.execute(
                """
                INSERT INTO task_ownership(
                    provider, task_id, principal_id, tenant_id, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider, task_id) DO UPDATE SET
                    principal_id = excluded.principal_id,
                    tenant_id = excluded.tenant_id
                """,
                (
                    provider,
                    task_id,
                    owner.principal_id,
                    owner.tenant_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._connection.commit()

    async def require_owner(self, provider: str, task_id: str, owner: AuthContext) -> None:
        async with self._lock:
            row = self._connection.execute(
                """
                SELECT principal_id, tenant_id FROM task_ownership
                WHERE provider = ? AND task_id = ?
                """,
                (provider, task_id),
            ).fetchone()
        if row is None:
            if owner.is_local:
                return
            raise PermissionError("Task is not owned by the current principal.")
        if row != (owner.principal_id, owner.tenant_id):
            raise PermissionError("Task is not owned by the current principal.")

    async def list_task_ids(self, provider: str, owner: AuthContext) -> set[str]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT task_id FROM task_ownership
                WHERE provider = ? AND principal_id = ? AND tenant_id = ?
                """,
                (provider, owner.principal_id, owner.tenant_id),
            ).fetchall()
        return {str(row[0]) for row in rows}

    async def prune(self, max_age_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        async with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM task_ownership WHERE created_at < ?",
                (cutoff,),
            )
            self._connection.commit()
        return cursor.rowcount if cursor.rowcount is not None else 0

    async def ping(self) -> None:
        async with self._lock:
            self._connection.execute("SELECT 1").fetchone()

    async def close(self) -> None:
        async with self._lock:
            self._connection.close()


class SQLiteTaskArtifactCache:
    """SQLite-backed cache mapping provider task IDs to persisted artifact refs."""

    def __init__(
        self,
        database_path: Path,
        *,
        ttl_seconds: int = 86_400,
        max_size: int = 10_000,
    ) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._ensure_schema()
        self._connection.commit()
        self._lock = asyncio.Lock()
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size

    def _ensure_schema(self) -> None:
        """Create or migrate the artifact cache to provider-scoped keys."""
        with self._connection:
            columns = {
                str(row[1])
                for row in self._connection.execute("PRAGMA table_info(task_artifacts)").fetchall()
            }
            legacy_exists = self._table_exists("task_artifacts_legacy")
            if columns and "provider" not in columns:
                if legacy_exists:
                    self._connection.execute(
                        """
                        INSERT OR REPLACE INTO task_artifacts_legacy
                        SELECT task_id, artifacts_json, created_at FROM task_artifacts
                        """
                    )
                    self._connection.execute("DROP TABLE task_artifacts")
                else:
                    self._connection.execute(
                        "ALTER TABLE task_artifacts RENAME TO task_artifacts_legacy"
                    )
                legacy_exists = True
            self._create_table()
            if legacy_exists:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO task_artifacts(
                        provider, task_id, artifacts_json, created_at
                    )
                    SELECT 'modelark', task_id, artifacts_json, created_at
                    FROM task_artifacts_legacy
                    """
                )
                self._connection.execute("DROP TABLE task_artifacts_legacy")

    def _table_exists(self, table: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            is not None
        )

    def _create_table(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_artifacts (
                provider TEXT NOT NULL,
                task_id TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(provider, task_id)
            )
            """
        )

    async def get(self, provider: str, task_id: str) -> dict[str, ArtifactRef | None] | None:
        async with self._lock:
            row = self._connection.execute(
                """
                SELECT artifacts_json, created_at FROM task_artifacts
                WHERE provider = ? AND task_id = ?
                """,
                (provider, task_id),
            ).fetchone()
        if row is None:
            return None
        artifacts_json, created_at_str = row
        created_at = datetime.fromisoformat(created_at_str)
        if (datetime.now(UTC) - created_at).total_seconds() > self._ttl_seconds:
            return None
        return self._deserialize(artifacts_json)

    async def set(
        self,
        provider: str,
        task_id: str,
        artifacts: dict[str, ArtifactRef | None],
    ) -> None:
        artifacts_json = self._serialize(artifacts)
        now = datetime.now(UTC).isoformat()
        async with self._lock:
            self._connection.execute(
                """
                INSERT INTO task_artifacts(provider, task_id, artifacts_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, task_id) DO UPDATE SET
                    artifacts_json = excluded.artifacts_json,
                    created_at = excluded.created_at
                """,
                (provider, task_id, artifacts_json, now),
            )
            self._connection.commit()
            count_row = self._connection.execute("SELECT COUNT(*) FROM task_artifacts").fetchone()
            if count_row is not None and count_row[0] > self._max_size:
                self._connection.execute(
                    """
                    DELETE FROM task_artifacts
                    WHERE (provider, task_id) NOT IN (
                        SELECT provider, task_id FROM task_artifacts
                        ORDER BY created_at DESC LIMIT ?
                    )
                    """,
                    (self._max_size,),
                )
                self._connection.commit()

    async def pop(self, provider: str, task_id: str) -> dict[str, ArtifactRef | None] | None:
        async with self._lock:
            row = self._connection.execute(
                """
                SELECT artifacts_json, created_at FROM task_artifacts
                WHERE provider = ? AND task_id = ?
                """,
                (provider, task_id),
            ).fetchone()
            if row is not None:
                self._connection.execute(
                    "DELETE FROM task_artifacts WHERE provider = ? AND task_id = ?",
                    (provider, task_id),
                )
                self._connection.commit()
        if row is None:
            return None
        created_at = datetime.fromisoformat(row[1])
        if (datetime.now(UTC) - created_at).total_seconds() > self._ttl_seconds:
            return None
        return self._deserialize(row[0])

    async def clear(self) -> None:
        async with self._lock:
            self._connection.execute("DELETE FROM task_artifacts")
            self._connection.commit()

    async def prune_expired(self) -> int:
        cutoff = (datetime.now(UTC) - timedelta(seconds=self._ttl_seconds)).isoformat()
        async with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM task_artifacts WHERE created_at < ?",
                (cutoff,),
            )
            self._connection.commit()
        return cursor.rowcount if cursor.rowcount is not None else 0

    async def close(self) -> None:
        async with self._lock:
            self._connection.close()

    @staticmethod
    def _serialize(artifacts: dict[str, ArtifactRef | None]) -> str:
        return json.dumps(
            {k: v.model_dump(mode="json") if v is not None else None for k, v in artifacts.items()}
        )

    @staticmethod
    def _deserialize(raw: str) -> dict[str, ArtifactRef | None]:
        data = json.loads(raw)
        return {
            k: ArtifactRef.model_validate(v) if v is not None else None for k, v in data.items()
        }


@dataclass(frozen=True, slots=True)
class CostEstimate:
    product: str
    amount_usd: float


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: int
    owner: AuthContext
    estimate: CostEstimate
    usage_date: date


class BudgetExceededError(ValueError):
    """Raised before dispatch when a principal's daily budget is exhausted."""


class BudgetLedger:
    """SQLite-backed daily budget reservations for one server instance."""

    def __init__(self, database_path: Path, *, daily_limit_usd: float | None = None) -> None:
        self._connection = sqlite3.connect(database_path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usage_date TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                product TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('reserved', 'committed', 'released'))
            )
            """
        )
        self._connection.commit()
        self._daily_limit_usd = daily_limit_usd
        self._lock = asyncio.Lock()

    async def reserve(
        self,
        owner: AuthContext,
        estimate: CostEstimate,
    ) -> BudgetReservation:
        usage_date = datetime.now(UTC).date()
        async with self._lock:
            row = self._connection.execute(
                """
                SELECT COALESCE(SUM(amount_usd), 0) FROM budget_reservations
                WHERE usage_date = ? AND principal_id = ? AND tenant_id = ?
                  AND status IN ('reserved', 'committed')
                """,
                (usage_date.isoformat(), owner.principal_id, owner.tenant_id),
            ).fetchone()
            current = float(row[0]) if row is not None else 0.0
            if (
                self._daily_limit_usd is not None
                and current + estimate.amount_usd > self._daily_limit_usd
            ):
                BUDGET_REJECTIONS.labels(product=estimate.product).inc()
                raise BudgetExceededError(
                    f"Daily budget of ${self._daily_limit_usd:.2f} would be exceeded."
                )
            cursor = self._connection.execute(
                """
                INSERT INTO budget_reservations(
                    usage_date, principal_id, tenant_id, product, amount_usd, status
                ) VALUES (?, ?, ?, ?, ?, 'reserved')
                """,
                (
                    usage_date.isoformat(),
                    owner.principal_id,
                    owner.tenant_id,
                    estimate.product,
                    estimate.amount_usd,
                ),
            )
            self._connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Budget reservation did not return an ID.")
            reservation_id = cursor.lastrowid
        return BudgetReservation(reservation_id, owner, estimate, usage_date)

    async def commit(self, reservation: BudgetReservation) -> None:
        await self._set_status(reservation, "committed")

    async def release(self, reservation: BudgetReservation) -> None:
        await self._set_status(reservation, "released")

    async def _set_status(
        self,
        reservation: BudgetReservation,
        status: Literal["committed", "released"],
    ) -> None:
        async with self._lock:
            self._connection.execute(
                "UPDATE budget_reservations SET status = ? WHERE id = ?",
                (status, reservation.reservation_id),
            )
            self._connection.commit()

    async def prune(self, max_age_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).date().isoformat()
        async with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM budget_reservations WHERE usage_date < ?",
                (cutoff,),
            )
            self._connection.commit()
        return cursor.rowcount if cursor.rowcount is not None else 0

    async def close(self) -> None:
        async with self._lock:
            self._connection.close()


@dataclass(slots=True)
class RuntimeServices:
    settings: Settings
    artifact_store: ArtifactStore
    safe_downloader: SafeDownloader
    ownership_store: TaskOwnershipStore
    budget_ledger: BudgetLedger
    provider_limiters: ProviderLimiters
    task_artifact_cache: TaskArtifactCache


@dataclass(slots=True)
class RuntimeState:
    runtime: RuntimeServices | None = None


def build_state_stores(
    settings: Settings,
    database_path: Path,
) -> tuple[TaskOwnershipStore, BudgetLedger, TaskArtifactCache]:
    """Build the state stores for the configured ``STATE_BACKEND``."""
    if settings.state_backend != "sqlite":
        raise ValueError(f"Unsupported STATE_BACKEND: {settings.state_backend}")
    log_warning(
        "single_instance_state_backend",
        backend=settings.state_backend,
        note="Only one replica may run with the SQLite state backend.",
    )
    return (
        SQLiteTaskOwnershipStore(database_path),
        BudgetLedger(database_path, daily_limit_usd=settings.daily_budget_usd or None),
        SQLiteTaskArtifactCache(
            database_path,
            ttl_seconds=settings.persistence_cache_ttl_seconds,
            max_size=settings.persistence_cache_max_size,
        ),
    )


async def create_runtime_services(settings: Settings) -> RuntimeServices:
    artifact_dir = Path(settings.artifact_dir).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    downloader = SafeDownloader(
        timeout=settings.request_timeout_ms / 1000,
        connect_timeout=settings.connect_timeout_ms / 1000,
    )
    if settings.artifact_backend == "object_storage":
        artifact_store: ArtifactStore = ObjectStorageArtifactStore(
            settings=settings,
            downloader=downloader,
        )
    else:
        artifact_store = FilesystemArtifactStore(
            artifact_dir=str(artifact_dir),
            ttl_seconds=settings.artifact_ttl_seconds,
            downloader=downloader,
        )
    database_path = artifact_dir / "runtime.sqlite3"
    ownership_store, budget_ledger, task_artifact_cache = build_state_stores(
        settings, database_path
    )
    return RuntimeServices(
        settings=settings,
        artifact_store=artifact_store,
        safe_downloader=downloader,
        ownership_store=ownership_store,
        budget_ledger=budget_ledger,
        provider_limiters=ProviderLimiters(
            provider_limit=settings.provider_max_concurrency,
            principal_limit=settings.principal_max_concurrency,
        ),
        task_artifact_cache=task_artifact_cache,
    )


async def close_runtime_services(runtime: RuntimeServices) -> None:
    await runtime.artifact_store.close()
    await runtime.ownership_store.close()
    await runtime.budget_ledger.close()
    await runtime.task_artifact_cache.close()


RuntimeFactory = Callable[[Settings], Awaitable[RuntimeServices]]


def get_runtime(ctx: Context) -> RuntimeServices:
    runtime = ctx.lifespan_context.get("runtime")
    if not isinstance(runtime, RuntimeServices):
        raise RuntimeError("Runtime services are unavailable outside the server lifespan.")
    return runtime


def get_principal(ctx: Context) -> PrincipalContext:
    """Derive application ownership from local mode or the verified token."""
    settings = get_runtime(ctx).settings
    if settings.mcp_auth_mode.value == "local":
        return PrincipalContext()

    token = get_access_token()
    if token is None:
        raise PermissionError("An authenticated access token is required.")
    claims = token.claims or {}
    principal_id = claims.get("sub") or token.subject or token.client_id
    tenant_id = claims.get(settings.mcp_tenant_claim)
    if not isinstance(principal_id, str) or not principal_id:
        raise PermissionError("The access token is missing a principal identity.")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise PermissionError(
            f"The access token is missing tenant claim '{settings.mcp_tenant_claim}'."
        )
    return PrincipalContext(
        principal_id=principal_id,
        tenant_id=tenant_id,
        scopes=frozenset(token.scopes),
        transport="http",
    )


@asynccontextmanager
async def billed_provider_slot(
    ctx: Context,
    *,
    provider: ProviderKey,
    product: str,
    estimated_cost_usd: float,
) -> AsyncIterator[None]:
    """Reserve budget and acquire shared limits around one billable call."""
    runtime = get_runtime(ctx)
    owner = get_principal(ctx)
    reservation = await runtime.budget_ledger.reserve(
        owner,
        CostEstimate(product=product, amount_usd=estimated_cost_usd),
    )
    try:
        async with runtime.provider_limiters.acquire(provider, owner):
            yield
    except ProviderError as exc:
        if exc.ambiguous_completion:
            await runtime.budget_ledger.commit(reservation)
        else:
            await runtime.budget_ledger.release(reservation)
        raise
    except Exception:
        await runtime.budget_ledger.release(reservation)
        raise
    else:
        await runtime.budget_ledger.commit(reservation)


async def _state_sweeper(runtime: RuntimeServices, settings: Settings) -> None:
    """Periodically sweep expired artifacts and prune aged state rows."""
    while True:
        await asyncio.sleep(settings.artifact_sweep_interval_seconds)
        try:
            deleted = await runtime.artifact_store.delete_expired(datetime.now(UTC))
            log_info("state_sweep_artifacts", deleted=deleted)
        except Exception as exc:
            log_warning("state_sweep_artifact_error", error=str(exc))
        try:
            pruned = await runtime.ownership_store.prune(settings.state_prune_max_age_days)
            log_info("state_sweep_ownership", pruned=pruned)
        except Exception as exc:
            log_warning("state_sweep_ownership_error", error=str(exc))
        try:
            pruned = await runtime.budget_ledger.prune(settings.state_prune_max_age_days)
            log_info("state_sweep_budget", pruned=pruned)
        except Exception as exc:
            log_warning("state_sweep_budget_error", error=str(exc))
        try:
            pruned = await runtime.task_artifact_cache.prune_expired()
            log_info("state_sweep_cache", pruned=pruned)
        except Exception as exc:
            log_warning("state_sweep_cache_error", error=str(exc))


def build_lifespan(
    settings: Settings,
    runtime_factory: RuntimeFactory = create_runtime_services,
    state: RuntimeState | None = None,
) -> Callable[
    [FastMCP[dict[str, object]]],
    AbstractAsyncContextManager[dict[str, object]],
]:
    @asynccontextmanager
    async def server_lifespan(
        _server: FastMCP[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]:
        runtime = await runtime_factory(settings)
        if state is not None:
            state.runtime = runtime
        sweeper = asyncio.create_task(_state_sweeper(runtime, settings))
        try:
            yield {"runtime": runtime}
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper
            if state is not None:
                state.runtime = None
            await close_runtime_services(runtime)

    return server_lifespan
