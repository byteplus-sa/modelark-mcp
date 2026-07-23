# Codebase Gap Remediation Handover

**Updated:** 2026-07-23
**Plan:** [`plans/PLAN_CODEBASE_GAP_REMEDIATION.md`](plans/PLAN_CODEBASE_GAP_REMEDIATION.md)
**Status:** implementation complete; release gates documented below

## Delivered

- Hardened provider-media ingestion with DNS validation, IP-pinned connects,
  per-hop redirect checks, MIME/size enforcement, and atomic persistence.
- Added versioned artifact ownership metadata and principal/tenant isolation.
- Replaced request/module globals with a FastMCP lifespan-owned runtime for the
  artifact store, downloader, task ownership, budget ledger, limiters, and
  bounded persistence cache.
- Added safe provider retry classification, exponential jitter, `Retry-After`
  support, and ambiguous-mutation protection.
- Added explicit success schemas and protocol-level structured error results.
- Replaced model-name capability inference with explicit model bindings.
- Added JWT verification, scoped tools/resources, fail-closed remote HTTP,
  Host/Origin enforcement, and streamed request-body limits.
- Added `/health`, `/ready`, `/metrics`, Prometheus instrumentation, and
  provider tracing hooks.
- Repaired live smoke scripts, locked packaging, container startup/health, and
  immutable GitHub Actions pins.
- Synchronized README, configuration, transport, deployment, API, integration,
  tool, and troubleshooting documentation with shipped behavior.

## Current architecture boundary

The filesystem artifact store and SQLite ownership/budget state are durable for
one process. Provider and principal semaphores and the cache are also
process-local. Run one replica. Horizontal scaling requires distributed
implementations for all of those runtime contracts; an object-store placeholder
is no longer advertised as implemented.

## Local release gate

```bash
uv lock --check
uv sync --locked --offline
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest --disable-socket --allow-unix-socket \
  --cov=modelark_mcp --cov-report=term-missing
uv run bandit -q -r src/modelark_mcp
uv run pip-audit --strict
uv run detect-secrets scan --baseline .secrets.baseline
uv build --offline
```

Expected test result: **459 passed**, with the configured branch-coverage floor
of 85% (current result: **88.08%**).

## Operational requirements

- stdio and loopback HTTP may use `MCP_AUTH_MODE=local`.
- Any non-loopback HTTP bind requires JWT JWKS URI, issuer, and audience.
- Tokens need `sub`, the configured tenant claim, and least-privilege scopes.
- The container defaults to protected HTTP/JWT mode and therefore requires
  verifier configuration at runtime.
- `/metrics` is intentionally unauthenticated for scraping; restrict it at the
  ingress/network layer where necessary.

## Remaining non-blocking work

- Implement distributed artifact/state/limiter adapters before adding replicas.
- Add the live provider smoke scripts to a protected, explicitly billable CI
  environment; they passed manually on 2026-07-23.
- Rotate immutable CI pins through reviewed dependency updates.

No commit was created as part of this remediation.
