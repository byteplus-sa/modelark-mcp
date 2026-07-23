# Runtime Services

The server lifespan owns a single `RuntimeServices` object
(`src/modelark_mcp/runtime.py`) that is built once at startup and closed at
shutdown. Every tool retrieves it via `get_runtime(ctx)`. This document
describes the five operational services it provides: concurrency limiting,
the daily budget ledger, Seedance task ownership, the persistence cache, and
the provider retry policy.

All state lives in a single SQLite database at
`<artifact_dir>/runtime.sqlite3` (default `artifact_dir` is `.artifacts`),
shared by the ownership store and the budget ledger. The synchronous
`sqlite3.Connection` behind each is guarded by a per-instance `asyncio.Lock`,
so these stores are **single-process only** — horizontal scaling requires a
distributed replacement.

## `RuntimeServices` fields

| Field | Type | Built from |
|---|---|---|
| `settings` | `Settings` | input settings |
| `artifact_store` | `FilesystemArtifactStore` | `FilesystemArtifactStore(artifact_dir, ttl_seconds, downloader)` |
| `safe_downloader` | `SafeDownloader` | `SafeDownloader(timeout, connect_timeout)` |
| `ownership_store` | `SQLiteTaskOwnershipStore` | `SQLiteTaskOwnershipStore(database_path)` |
| `budget_ledger` | `BudgetLedger` | `BudgetLedger(database_path, daily_limit_usd)` |
| `provider_limiters` | `ProviderLimiters` | `ProviderLimiters(provider_limit, principal_limit)` |
| `persistence_cache` | `TTLCache[str, dict[str, ArtifactRef \| None]]` | hard-coded `maxsize=10_000`, `ttl=86_400` |

`close_runtime_services` closes exactly three subsystems in order:
`artifact_store`, `ownership_store`, `budget_ledger`. The `SafeDownloader`
is closed **indirectly** — `FilesystemArtifactStore.close()` calls
`self._downloader.close()`. The provider/principal limiters have no close
method (semaphores require no cleanup).

## Concurrency limiters (`ProviderLimiters`)

Two distinct layers, acquired together for every billable call:

- **Provider-level** — one global `asyncio.Semaphore` per provider bucket.
  There are exactly two buckets, `"modelark"` and `"seed-speech"`, each
  independently sized to `provider_limit`. So the default cap is **5
  concurrent ModelArk calls AND 5 concurrent Seed Speech calls**
  (independent pools, not a shared 5).
- **Principal-level** — one `asyncio.Semaphore(principal_limit)` per
  principal, lazily created and stored in a `TTLCache` keyed by
  `"<tenant_id>\0<principal_id>"` (NUL-separated). Cache get/create is
  guarded by an `asyncio.Lock`.

`acquire(provider, owner)` is an async context manager that holds **both**
the provider bucket semaphore and the principal's semaphore for the duration
of the call.

| Env var | Default | Constraint | Used as |
|---|---|---|---|
| `PROVIDER_MAX_CONCURRENCY` | `5` | `ge=1` | per-bucket provider limit |
| `PRINCIPAL_MAX_CONCURRENCY` | `3` | `ge=1` | per-principal limit |

The per-principal semaphore cache defaults to `maxsize=10_000` and
`ttl=86_400` (24h); idle principal semaphores expire after 24h. A `TTLCache`
eviction of a held semaphore dereferences it from the cache but does not
cancel its waiters.

> For parallel variation tools, a third local `asyncio.Semaphore(max_concurrent=5)`
> is created per batch by `run_variation_batch` (see [Parallel
> variations](#parallel-variations)). It composes with — and is independent
> of — these provider/principal limiters.

## Daily budget + cost estimation

### Budget ledger (`BudgetLedger`)

SQLite-backed, same file as the ownership store. Schema:

```sql
CREATE TABLE budget_reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usage_date TEXT NOT NULL,        -- UTC date (ISO)
    principal_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    product TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'committed', 'released'))
)
```

Three-state lifecycle: `reserved` → `committed` (charged) **or**
`reserved` → `released` (rolled back). Only rows with `status IN
('reserved', 'committed')` count against the limit.

- `reserve(owner, estimate)` — sums the principal's spend for the current
  UTC date; if a configured limit exists and `current + amount` would exceed
  it, increments `modelark_mcp_budget_rejections_total{product}` and raises
  `BudgetExceededError` **before** the provider is called. Otherwise inserts
  a `reserved` row and returns a `BudgetReservation`.
- `commit(reservation)` — marks the row `committed`.
- `release(reservation)` — marks the row `released`.

| Env var | Default | Behavior |
|---|---|---|
| `DAILY_BUDGET_USD` | `0.0` | Per-principal UTC daily limit. `0.0` (and any falsy value) normalizes to `None` → **record-only mode** (no rejection; the ledger still records everything). A positive value enables **reject mode**. |

The daily window is the UTC calendar date, scoped per `(principal_id, tenant_id)`.

### Cost estimation (`tools/_cost.py`)

The estimator used by parallel variation tools. Costs are per product and
per variation only — there is **no per-model or per-family cost table**.

| Constant | Value |
|---|---|
| `COST_PER_IMAGE` | `0.03` USD |
| `COST_PER_AUDIO_SECOND` | `0.0031` USD |
| `COST_PER_VIDEO_TASK` | `0.07` USD |
| `DEFAULT_MAX_CONCURRENT` | `5` |

`estimate_cost(product, variations, duration_seconds=0.0)`:

| `product` | Formula |
|---|---|
| `"image"` | `round(variations * 0.03, 2)` |
| `"audio"` | `round(variations * max(duration_seconds, 10) * 0.0031, 2)` — **floor of 10 seconds per variation** |
| `"video"` | `round(variations * 0.07, 2)` |
| (any other) | `0.0` |

> Note: `SeedreamFamily` (`pro`/`lite`/`4x`) and `SeedanceFamily`
> (`standard`/`fast`/`mini`) are model-binding constructs defined in
> `config/env.py`, **not** cost tiers. They do not affect the estimate.

## Seedance task ownership (`SQLiteTaskOwnershipStore`)

Ownership of asynchronous Seedance task IDs, so one principal cannot read,
cancel, or delete another's tasks. Schema:

```sql
CREATE TABLE IF NOT EXISTS task_ownership (
    task_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

| Method | Behavior |
|---|---|
| `record(task_id, owner)` | `INSERT ... ON CONFLICT(task_id) DO UPDATE` — re-recording **upserts** to the new owner (the closest thing to a transfer). |
| `require_owner(task_id, owner)` | Row missing: if `owner.is_local` returns silently (local mode is permissive for unrecorded tasks), else `PermissionError`. Row present but mismatched: `PermissionError("Task is not owned by the current principal.")`. |
| `list_task_ids(owner)` | returns all `task_id`s for `(principal_id, tenant_id)`. |
| `ping()` | `SELECT 1` liveness probe (used by the `/ready` route). |
| `close()` | closes the connection. |

Every query is scoped by **both** `principal_id` **and** `tenant_id`, and
the `is_local` shortcut only affects the missing-row branch — a row that
exists and belongs to someone else still raises, even in local mode.

> This is distinct from **artifact ownership**, which is stored in
> `.meta.json` sidecars next to the artifact bytes
> (`artifacts/filesystem_store.py`). See [artifacts.md](artifacts.md).

## Persistence cache

`RuntimeServices.persistence_cache` is a `TTLCache(maxsize=10_000,
ttl=86_400)` — hard-coded, not exposed via `Settings`. It caches provider
task lookups → artifact references (`dict[str, ArtifactRef | None]`). The
24h TTL matches the longest provider media-URL expiry window (24h for
image/video; audio URLs expire in 2h), so resolved artifact references for a
provider task ID are not re-resolved while still valid.

## Retry policy (`providers/retry.py`)

`RetryPolicy` is a frozen dataclass with hard-coded defaults (no env vars):

| Field | Default |
|---|---|
| `max_attempts` | `3` |
| `base_delay_seconds` | `0.25` |
| `max_delay_seconds` | `4.0` |
| `jitter_ratio` | `0.2` |

`call_with_retry(operation, *, policy=None, sleep=asyncio.sleep,
random_value=random.random)`:

- **Only `ProviderError` is retried**, and only when `exc.retryable` **and**
  `not exc.ambiguous_completion` **and** `attempt < max_attempts`.
  `ambiguous_completion=True` is deliberately non-retryable: the mutation
  may have already succeeded at the provider, so a blind retry could
  double-charge or duplicate. Reconcile via the task ID / request ID instead.
- Any non-`ProviderError` propagates immediately (no retry, no wrapping).
- **Backoff**:
  - If `exc.error.retry_after_seconds is not None` (provider `Retry-After`):
    `delay = min(retry_after_seconds, max_delay_seconds)` — **no jitter**.
  - Otherwise exponential with symmetric jitter:
    `base = min(base_delay * 2**(attempt-1), max_delay)`;
    `jitter = base * jitter_ratio * (random*2 - 1)`;
    `delay = max(0.0, base + jitter)`.
- Each retry increments `modelark_mcp_retry_attempts_total{provider, operation}`.

## Billable call composition (`billed_provider_slot`)

A single async context manager ties the above together:

```python
async with billed_provider_slot(ctx, provider=..., product=..., estimated_cost_usd=...):
    # 1. reserve budget  (raises BudgetExceededError before dispatch if over)
    # 2. acquire provider + principal semaphores
    # 3. (caller runs the provider call, typically via call_with_retry)
```

Outcome handling:

| Outcome | Budget action |
|---|---|
| Success | `commit` (charged) |
| `ProviderError` with `ambiguous_completion` | `commit` (treats as billable — may have succeeded) |
| `ProviderError` without ambiguous completion | `release` |
| Any other exception | `release` |

In all error cases the exception is re-raised.

## Error taxonomy

| Class | Module | Raised by | Meaning |
|---|---|---|---|
| `ProviderError` | `domain/errors.py` | provider gateways + transport normalizers | wraps a `NormalizedProviderError`; the single retryable error type |
| `BudgetExceededError` | `runtime.py` (extends `ValueError`) | `BudgetLedger.reserve` | daily budget would be exceeded; raised before dispatch |
| `ValueError` | builtin | `ProviderLimiters`, `RetryPolicy`, `resolve_prompts` | config/argument validation |
| `RuntimeError` | builtin | `get_runtime`, `BudgetLedger.reserve` | missing runtime services / reservation ID |
| `PermissionError` | builtin | `get_principal`, `require_owner` | missing token, missing principal/tenant claims, ownership mismatch |

`NormalizedProviderError` carries: `provider` (`modelark` or `seed-speech`),
`operation`, `http_status`, `code`, `message`, `request_id`, `retryable`,
`ambiguous_completion`, `retry_after_seconds`. Transport-layer normalizers in
`BaseHttpGateway`:

| Method | `code` | `retryable` | `ambiguous_completion` |
|---|---|---|---|
| `normalize_timeout` | `TIMEOUT` | `False` | `True` |
| `normalize_connection_error` | `CONNECTION_ERROR` | `True` | `None` |
| `normalize_transport_error` | `TRANSPORT_ERROR` | `True` | `None` |

So timeouts are non-retryable and ambiguous (may have succeeded); connection
and transport errors are retryable and non-ambiguous.

## Parallel variations (`tools/_parallel.py`)

Re-exports `DEFAULT_MAX_CONCURRENT = 5`.

- **`generate_seeds(base_seed, count)`** — `None` → provider-randomized (seed
  not recorded); `-1` → per-variation `secrets.randbelow(2**31)` (recorded);
  `N` → deterministic `(N + i) % 2**31`.
- **`resolve_prompts(base_prompt, variation_prompts, count)`** — uses
  `variation_prompts` if given; else `[base_prompt] * count`; raises if
  neither is provided.
- **`gather_with_timeout(coros, timeout)`** — per-coroutine
  `asyncio.wait_for` + `asyncio.gather(..., return_exceptions=True)`; returns
  exceptions and `asyncio.TimeoutError` **as elements**, never raises.
- **`run_variation_batch(count, timeout, factory, *, max_concurrent=5)`** —
  local `asyncio.Semaphore(max_concurrent)` around `factory(idx)`; maps each
  outcome into a `VariationResult` (`TIMEOUT` / `GATHER_ERROR` codes for
  failures the helper detects). A variation counts as succeeded iff it
  produced an `artifact` **or** a `task_id`. Returns `VariationSummary(total,
  succeeded, failed, variations)`. One variation failing never breaks the
  others; the batch always returns exactly `count` entries.

See [api-reference.md](api-reference.md) for `VariationResult` /
`VariationSummary` / `VariationError` field tables.
