# Architecture

This document describes the structure of the ModelArk Seed Multimodal MCP
Server as shipped today. For the original design rationale, see
[../plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md](../plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md).

## Design goals

- **Small, typed tool surface** — a handful of Pydantic-validated tools rather
  than a wide REST API.
- **Dedicated provider gateways, one domain layer** — Seedance and Seedream
  share the ModelArk host and Bearer auth; Seed Audio uses a separate host and
  `X-Api-Key`; VOD AI MediaKit uses its own Bearer-authenticated convenience
  endpoint. The differences are hidden behind normalized adapters.
- **Durable artifacts** — known provider media URLs expire (2h audio, 24h
  ModelArk image/video), so outputs are persisted to a local store and
  re-exposed as stable `seed-media://artifacts/{id}` MCP resources. MediaKit
  source lifetime is unconfirmed and its persistence is best-effort.
- **Safe by default** — local `stdio` requires no auth; remote HTTP requires
  JWT verification, Host/Origin protection, and body limits.
- **Observable and budget-aware** — structured logs, Prometheus metrics, and a
  per-principal daily budget ledger.

## Layered structure

```text
src/modelark_mcp/
├── __main__.py            # entry point; truststore injection; transport wiring
├── server.py              # FastMCP factory; tool/resource/route registration
├── config/                # settings (env), model capability registry
│   ├── env.py
│   └── model_capabilities.py
├── domain/                # pure models: ArtifactRef, MediaSource, errors
│   ├── artifacts.py
│   ├── media.py
│   ├── models.py
│   └── errors.py
├── tools/                 # MCP tool implementations (+ _cost, _parallel, _errors)
├── providers/             # dedicated HTTP gateways + retry policy
│   ├── base.py            # BaseHttpGateway: spans, metrics, error normalization
│   ├── retry.py
│   ├── modelark.py        # Seedream + Seedance
│   └── seed_speech.py     # Seed Audio
├── runtime.py             # lifespan-owned services (limiter, budget, ownership)
├── artifacts/             # durable artifact store (filesystem backend)
│   ├── store.py           # ArtifactStore protocol
│   └── filesystem_store.py
├── security/              # auth, SSRF-safe downloads, URL/media policy, body limit
├── observability/         # structured logging + Prometheus metrics
└── transports (via FastMCP) # stdio + Streamable HTTP
```

## Provider gateway domain layer

```mermaid
flowchart LR
    Client["MCP Client\n(stdio / HTTP)"] --> Server["FastMCP server\n(server.py)"]
    Server --> Domain["Domain layer\n(tools/ + domain/)"]
    Domain --> Gateway["Provider gateways\n(providers/)"]
    Gateway -->|"Bearer auth"| ModelArk["ModelArk\nSeedream + Seedance"]
    Gateway -->|"X-Api-Key"| SeedSpeech["Seed Speech\nSeed Audio"]
    Gateway -->|"Bearer auth"| MediaKit["VOD AI MediaKit\nvideo enhancement"]
    Server -.durable.-> Store["Artifact store\n(filesystem)"]
    Server -.state.-> Runtime["Runtime services\n(runtime.py)"]
```

- **ModelArk gateway** (`providers/modelark.py`) — serves Seedream (image)
  and Seedance (video). Uses `Authorization: Bearer` and base URL
  `https://ark.ap-southeast.bytepluses.com/api/v3`.
- **Seed Speech gateway** (`providers/seed_speech.py`) — serves Seed Audio.
  Uses `X-Api-Key` and base URL `https://voice.ap-southeast-1.bytepluses.com`.
- **VOD AI MediaKit gateway** (`providers/vod_mediakit/`) — serves the
  asynchronous `vod_enhance_video` submission endpoint. It uses Bearer auth
  and defaults to
  `https://mediakit.ap-southeast-1.bytepluses.com/api/v1`. Its success schema
  is provisional and isolated in the adapter; the gateway accepts only known
  result aliases and rejects unknown shapes.
- These gateways extend `BaseHttpGateway` (`providers/base.py`), which wraps every
  outbound request in an OpenTelemetry span, records Prometheus
  provider metrics, and normalizes transport/HTTP errors into a single
  `ProviderError` carrying a `NormalizedProviderError`.

MediaKit enhancement is a non-idempotent mutation and bypasses the automatic
retry helper: a timeout can be ambiguous after the provider has begun work.
The current integration accepts asynchronous task submission and exposes no
polling tool because none is verified for this Bearer surface. If a completed
result is returned, the provider URL is preserved and persistence is
attempted separately as a best-effort operation under the 200 MiB video limit.

## Server lifecycle and runtime services

`server.py::create_server` builds the FastMCP instance. The server lifespan
is owned by `runtime.py::build_lifespan`, which constructs a single
`RuntimeServices` object and yields it as the FastMCP lifespan context:

```mermaid
sequenceDiagram
    participant M as __main__ / FastMCP
    participant L as build_lifespan
    participant R as RuntimeServices
    participant T as Tool call
    M->>L: start lifespan
    L->>R: create_runtime_services(settings)
    L->>M: yield {"runtime": RuntimeServices}
    M->>T: invoke tool
    T->>R: get_runtime(ctx)
    R-->>T: services
    T->>T: billed_provider_slot(...)
    M->>L: shutdown
    L->>R: close_runtime_services (artifact_store, ownership_store, budget_ledger, task_artifact_cache)
```

`RuntimeServices` holds seven components (see [runtime.md](runtime.md) for
full detail):

| Field | Purpose |
|---|---|
| `settings` | resolved `Settings` |
| `artifact_store` | `FilesystemArtifactStore` — durable media |
| `safe_downloader` | SSRF-safe HTTP downloader |
| `ownership_store` | `SQLiteTaskOwnershipStore` — Seedance task ownership |
| `budget_ledger` | `BudgetLedger` — per-principal UTC daily budget |
| `provider_limiters` | `ProviderLimiters` — provider + principal concurrency |
| `task_artifact_cache` | `SQLiteTaskArtifactCache` — provider task → artifact ref cache |

`close_runtime_services` closes exactly four of these: `artifact_store`,
`ownership_store`, `budget_ledger`, and `task_artifact_cache`.

## Request flow for a billable tool

```mermaid
flowchart TD
    A["MCP tool invoked"] --> B{"local mode?"}
    B -->|yes| C["PrincipalContext()\nlocal/local"]
    B -->|no| D["get_access_token()\nverify sub + tenant claim"]
    D --> C2["PrincipalContext(principal, tenant, scopes)"]
    C --> E["reserve budget\n(BudgetLedger.reserve)"]
    C2 --> E
    E -->|"over limit"| F["BudgetExceededError\n(pre-dispatch)"]
    E -->|"reserved"| G["acquire provider + principal\nsemaphores (billed_provider_slot)"]
    G --> H["call_with_retry\n(provider gateway)"]
    H --> I{"outcome"}
    I -->|success| J["commit reservation"]
    I -->|"ambiguous timeout"| J
    I -->|"retryable error"| K["release reservation"]
    J --> L["persist artifact + return ArtifactRef"]
    K --> L
```

Three layers of control compose on a single billable call: the provider
bucket semaphore (per provider, global, default 5), the principal semaphore
(per `(tenant, principal)`, default 3), and — for parallel variation tools — a
per-batch local semaphore (`max_concurrent=5`). See [runtime.md](runtime.md).

## Transports

| Transport | When | Auth |
|---|---|---|
| `stdio` | local default | none (single trusted principal `local`) |
| Streamable HTTP | remote / shared | JWT verification required for non-loopback hosts |

`truststore.inject_into_ssl()` runs at module import in both `server.py` and
`__main__.py`, so every run path loads the macOS system Keychain for TLS.
Transport wiring, Host/Origin protection, and body-limit middleware live in
`__main__.py`. See [transports.md](transports.md) and [security.md](security.md).

## Where to read more

| Topic | Document |
|---|---|
| Runtime services (limiter, budget, ownership, retry) | [runtime.md](runtime.md) |
| Logging, metrics, tracing | [observability.md](observability.md) |
| Consolidated security model | [security.md](security.md) |
| Model capability registry | [models.md](models.md) |
| Durable artifact lifecycle | [artifacts.md](artifacts.md) |
| Tool contracts | [api-reference.md](api-reference.md) |
| Configuration | [configuration.md](configuration.md) |
