---
title: Concurrency and Timeout Remediation
type: plan
status: implemented
created: 2026-09-03
updated: 2026-09-04
tags:
  - concurrency
  - timeout
  - asyncio
  - sqlite
  - upload
  - fastmcp
  - modelark
related:
  - plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md
  - plans/PLAN_PARALLEL_GENERATION.md
  - plans/PLAN_CODEBASE_GAP_REMEDIATION.md
---

# Concurrency and Timeout Remediation

## Outcome

Fix the observed failure mode where parallel MCP tool calls hit client-side
timeouts ("the server serializes under load"), and resolve the upload
scope-review flag on large reference media. The server should dispatch
independent generation calls concurrently up to the provider's advertised
limit, keep the event loop responsive under concurrent SQLite access, and not
reject legitimate large uploads at the HTTP body boundary.

## Root-Cause Analysis

The claim "the server serializes under load" is **not** caused by the MCP
dispatch layer. Evidence from the installed FastMCP 3.4.4 and `mcp` SDK:

- The low-level server dispatches each incoming message concurrently:

```679:690:.venv/lib/python3.12/site-packages/mcp/server/lowlevel/server.py
            async with anyio.create_task_group() as tg:
                try:
                    async for message in session.incoming_messages:
                        logger.debug("Received message: %s", message)

                        tg.start_soon(
                            self._handle_message,
                            message,
                            session,
                            lifespan_context,
                            raise_exceptions,
                        )
```

- FastMCP's `server.py` has no lock/semaphore around `call_tool` (grep for
  `asyncio.Lock` / `anyio.Lock` / `Semaphore` returns no matches). Tool
  handlers run concurrently.

The serialization and timeouts come from four concrete, verifiable sources.

### 1. Per-principal limiter collapses all local calls into one pool

`ProviderLimiters` (`src/modelark_mcp/runtime.py`) enforces two layers:

```44:67:src/modelark_mcp/runtime.py
    def __init__(
        self,
        *,
        provider_limit: int = 5,
        principal_limit: int = 3,
        ...
    ) -> None:
        ...
        self._principal_limit = principal_limit
```

In stdio mode (and HTTP local mode), **every request is the same principal**
(`PrincipalContext()` defaults `principal_id="local"`). The per-principal
`asyncio.Semaphore(3)` therefore caps **all** concurrent calls — across every
provider — at 3, regardless of the per-provider limit of 5. When a client
fires N > 3 parallel generations, N − 3 calls queue on the principal
semaphore. Combined with Seedream Pro / Seed Audio synchronous latencies of
60–150 s, this produces head-of-line blocking that looks exactly like
"serializes under load." This is the primary in-server cause.

### 2. Synchronous SQLite runs on the event loop, serialized per store

`SQLiteTaskOwnershipStore`, `SQLiteObjectKeyOwnershipStore`,
`SQLiteTaskArtifactCache`, and `BudgetLedger` (`src/modelark_mcp/runtime.py`)
each hold a plain synchronous `sqlite3.Connection` guarded by one
`asyncio.Lock`. `BudgetLedger.reserve` runs inside `billed_provider_slot`,
which wraps **every** billable call, so every generation serializes through
one lock + a synchronous `sqlite3` commit executed in the event-loop thread.
No `journal_mode=WAL`, no `busy_timeout`, no `asyncio.to_thread` offload
(confirmed: `to_thread` appears only in the TOS/S3 object-storage gateways).

### 3. Client-side default timeouts are shorter than provider latency

Seedream Pro and Seedance synchronous generation take 60–150 s (longer under
cold start/queue), per the `request_timeout_ms` docs
(`config/env.py` default `600000`). Most MCP clients apply a per-tool default
request timeout (~60 s). A client "MCP timeout" is therefore often a
**client-side abort while the server keeps running**, not server
serialization. This must be documented and mitigated, not silently absorbed.

### 4. HTTP body limit vs. media limit mismatch on upload

`media_upload` (`src/modelark_mcp/tools/media_upload.py`) advertises video
uploads against `MediaLimits.video_max_bytes = 200 MiB`
(`security/media_policy.py`), but the ASGI `RequestBodyLimitMiddleware` is
wired to `mcp_http_max_body_bytes`, default `10_485_760` (10 MiB,
`config/env.py`). Over HTTP, a Base64 body inflates ~1.33× inside the JSON-RPC
envelope, so any upload much above ~7.5 MiB is rejected at the body limit —
even though the tool schema accepts up to 200 MiB. This is the concrete,
verifiable mismatch behind the "greatsword upload flagged" symptom. (If
"scope review" additionally refers to content moderation, that is orthogonal
and out of scope here.)

## Design Decisions

1. **Local mode must not self-throttle below the provider limit.** For a
   single trusted local principal, the per-principal semaphore is redundant
   with the provider semaphore and should not be a tighter bound. Skip the
   per-principal semaphore for local principals, or size it to at least the
   provider limit. Keep the per-principal bound meaningful for JWT/multi-tenant
   HTTP mode.

2. **Offload all synchronous SQLite access off the event loop and enable WAL.**
   Keep the `sqlite3` stdlib backend (no new dependency) but wrap queries in
   `asyncio.to_thread` and enable `PRAGMA journal_mode=WAL` +
   `busy_timeout`. This removes event-loop blocking and writer serialization.

3. **Do not retry, but reconcile, when a timeout is ambiguous.** Preserve the
   existing `ambiguous_completion` semantics; the fix is to stop producing the
   ambiguous timeouts (see 1–2) and to document client-timeout behavior.

4. **Reconcile the upload body limit with the media limit, and push large
   media off JSON-RPC where possible.** Raise `mcp_http_max_body_bytes` to
   cover the 200 MiB video path, and strengthen the skill/docs guidance to use
   the presign + client-side PUT pattern for large references (already
   documented in `.claude/skills/modelark-mcp/SKILL.md`, but the body cap
   defeats it).

## Implementation Tasks

### Task A: Fix per-principal self-throttling in local mode

**Files:** `src/modelark_mcp/runtime.py`

- [x] In `ProviderLimiters.acquire`, when `owner.is_local`, acquire only the
  provider semaphore (skip the principal semaphore).
- [x] Keep the per-principal semaphore for non-local principals.
- [x] Update `docs/runtime.md` "Concurrency limiters" section to state that the
  per-principal limit applies to authenticated HTTP principals only; local
  stdio is bounded solely by the provider limit.
- [x] Test: two concurrent local calls to the same provider up to
  `provider_limit` all proceed; a `principal_limit=1` fixture still serializes
  two distinct JWT principals.

**Acceptance:** `PROVIDER_MAX_CONCURRENCY=5` local runs admit 5 concurrent
ModelArk calls.

### Task B: Offload SQLite + WAL

**Files:** `src/modelark_mcp/runtime.py`

- [x] Add a shared helper that opens the connection with
  `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` and a
  `check_same_thread=False` connection.
- [x] Replace direct `self._connection.execute(...)` calls inside `async`
  methods with `await asyncio.to_thread(self._execute, ...)` (or a small
  `_run_sync` wrapper) for `SQLiteTaskOwnershipStore`,
  `SQLiteObjectKeyOwnershipStore`, `SQLiteTaskArtifactCache`, and
  `BudgetLedger`.
- [x] Keep the per-store `asyncio.Lock` only where a logical transaction spans
  multiple statements (e.g. `BudgetLedger.reserve`'s read-then-insert), and
  ensure the lock is held across the offloaded block, not the event loop.
- [x] Update `docs/runtime.md` "single-process only" note to mention WAL and
  thread-offloaded access.

**Acceptance:** a micro-benchmark/test asserting SQLite methods return
promptly without blocking the loop (`asyncio.wait_for` on a concurrent sleep
completes while a commit runs).

### Task C: Document client-timeout behavior

**Files:** `docs/troubleshooting.md`, `docs/configuration.md`,
`.claude/skills/modelark-mcp/SKILL.md`

- [x] Add a "Client timeouts vs provider latency" section: Seedream Pro /
  Seedance synchronous generation can exceed 60 s; a client MCP timeout does
  not mean the server failed, and the server keeps running. Prefer the async
  Seedance `create → poll` flow and `seedance_get_task` for long operations.
- [x] Correct `docs/troubleshooting.md:84` (currently claims the default is
  `BYTEPLUS_REQUEST_TIMEOUT_MS=300000`; actual default is `600000`).
- [x] Note in `docs/configuration.md` that `PRINCIPAL_MAX_CONCURRENCY` does not
  throttle the local stdio principal after Task A.

**Acceptance:** docs match shipped behavior.

### Task D: Reconcile upload body limit

**Files:** `src/modelark_mcp/config/env.py`, `docs/configuration.md`,
`.claude/skills/modelark-mcp/SKILL.md`

- [x] Raise `mcp_http_max_body_bytes` default to cover the video path
  (≥ 200 MiB + JSON-RPC/Base64 overhead, e.g. `268_435_456`), or add a
  dedicated `media_upload` path that accepts a presigned PUT instead of
  inlining Base64.
- [x] Add a validator warning when `mcp_http_max_body_bytes` is smaller than
  `MediaLimits.video_max_bytes * 4 // 3` (Base64 inflation) to fail fast on
  misconfiguration.
- [x] Strengthen skill/docs guidance: for large video references, use
  `media_upload` with `file_path` (stdio) or the presign + direct-upload
  pattern; the JSON-RPC body limit bounds only inlined Base64.

**Acceptance:** a 200 MiB video upload is not rejected by the HTTP body limit
(when the operator raises the cap), and misconfiguration produces a clear
startup error.

## Validation

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest --disable-socket --allow-unix-socket --cov=modelark_mcp --cov-report=term-missing
```

Coverage must stay ≥ 85% (`pyproject.toml:124`).

## Sources

- `mcp/server/lowlevel/server.py` (installed, v3.4.4 era) — concurrent
  `tg.start_soon` dispatch, lines 679–690.
- `src/modelark_mcp/runtime.py` — `ProviderLimiters`, SQLite stores.
- `src/modelark_mcp/config/env.py` — `PROVIDER_MAX_CONCURRENCY` (5),
  `PRINCIPAL_MAX_CONCURRENCY` (3), `mcp_http_max_body_bytes` (10 MiB),
  `request_timeout_ms` (600000).
- `src/modelark_mcp/security/media_policy.py` — `MediaLimits.video_max_bytes`
  (200 MiB).
- `docs/runtime.md`, `docs/transports.md`, `docs/troubleshooting.md`.
