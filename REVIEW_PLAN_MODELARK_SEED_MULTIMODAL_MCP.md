---
title: Review of PLAN_MODELARK_SEED_MULTIMODAL_MCP
type: review
status: open
created: 2026-07-20
updated: 2026-07-20
review_pass: 4
tags:
  - byteplus
  - modelark
  - mcp
  - fastmcp
  - python
  - uv
  - review
source:
  - plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md
  - https://gofastmcp.com/servers/tools
  - https://gofastmcp.com/servers/resources
  - https://gofastmcp.com/deployment/running-server
  - https://gofastmcp.com/more/settings
  - https://docs.byteplus.com/en/docs/ModelArk/1298459
  - https://docs.byteplus.com/en/docs/ModelArk/1541523
  - https://docs.byteplus.com/en/docs/ModelArk/1520757
---

<!-- markdownlint-disable MD013 MD025 -->

# Review of PLAN_MODELARK_SEED_MULTIMODAL_MCP

Review of `plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md` against current FastMCP
(v3.x) best practices and the official BytePlus ModelArk / Seed Speech API
documentation. Four passes were performed.

FastMCP claims were verified against the official FastMCP documentation via
Context7 library `/prefecthq/fastmcp` (accessed 2026-07-20). BytePlus API
claims were verified against the official BytePlus docs index bundled with the
`byteplus-docs` skill (accessed 2026-07-20).

## Summary

| Area | Status |
|---|---|
| BytePlus API inventory (hosts, auth, methods, fields, states, lifetimes) | Verified correct |
| Two-gateway split (Seed Speech `X-Api-Key` vs ModelArk Bearer) | Correct |
| Language stack consistency (Python / uv / FastMCP) | Fixed (pass 2) |
| FastMCP `ToolAnnotations` naming and per-tool annotations | Fixed (pass 3) |
| FastMCP `Context` in all six tool contracts | Fixed (pass 3) |
| FastMCP inline-media helpers (`Image` / `Audio`) | Fixed (pass 3) |
| FastMCP resource binary MIME (`ResourceResult` / `ResourceContent`) | Fixed (pass 3) |
| FastMCP settings / `.env` wiring | Fixed (pass 3) |
| `AbortSignal` JavaScript-ism | Fixed (pass 3) |
| `fastmcp.json` contents + `respx` dev dep | Fixed (pass 3) |
| `ToolAnnotations` import path | Fixed (pass 4) |
| Resource handler undefined `ctx_auth` | Fixed (pass 4) |
| Tool return-type vs composite-result tension | Open — see PA4-1 |

## Pass 1 — Critical (resolved)

### PA1-1 Language and stack contradiction — FIXED

The plan originally described a Python/FastMCP/uv server in its architecture,
contracts, and repo structure, but specified a TypeScript/Node.js stack in
Phase 1 (`npm init`, `@modelcontextprotocol/sdk`, `tsx`, `vitest`), Phase 2
(`undici`, `MockAgent`, Zod), Phase 3 (Zod cross-field rules), the Test Matrix
(Zod bounds), and Sources (MCP TypeScript SDK, Node.js LTS). The surrounding
repo files (`AGENTS.md`, `README.md`, `Makefile`) also said TypeScript.

**Pass 2 confirmation:** Fixed. Phase 1 now uses `uv init --lib` / `uv add`;
Phase 2 uses `httpx` + `MockTransport`; Phase 3 uses Pydantic model validators
and `ToolAnnotations`; the Test Matrix references Pydantic model validators;
Sources cite FastMCP documentation; `AGENTS.md`, `README.md`, and the
`Makefile` are all Python/uv/FastMCP.

## Pass 2 — Open findings (all fixed)

### PA2-1 `AbortSignal` is a JavaScript-ism — FIXED

**Location:** `Errors, Timeouts, and Retries` (plan line 667).

The plan said "Wire MCP cancellation through `AbortSignal`." In FastMCP/Python,
cancellation flows through `Context` and `asyncio.CancelledError`.

**Fix applied:** Plan line 667 now reads:

> Wire MCP cancellation through `ctx: Context` and `asyncio.CancelledError`.
> Cancelling the local request does not imply upstream Seedance task
> cancellation; that requires the explicit cancel tool. Translate client
> cancellation into `httpx` request abort by cancelling the awaiting task.

### PA2-2 `ToolAnnotations` field naming is wrong — FIXED

**Locations:** All six tool contracts + Phase 3 acceptance.

The plan used `destructive_hint=True` (snake_case). FastMCP follows the MCP
specification's camelCase: `readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`.

**Fix applied:** All six tools now declare `ToolAnnotations` with correct
camelCase fields, plus a summary table (plan lines 452-463):

| Tool | `readOnlyHint` | `destructiveHint` | `idempotentHint` | `openWorldHint` |
|---|---|---|---|---|
| `seed_audio_generate` | `False` | `False` | `False` | `True` |
| `seedream_generate_image` | `False` | `False` | `False` | `True` |
| `seedance_create_task` | `False` | `False` | `False` | `True` |
| `seedance_get_task` | `True` | `False` | `True` | `False` |
| `seedance_list_tasks` | `True` | `False` | `True` | `False` |
| `seedance_cancel_or_delete_task` | `False` | `True` | `False` | `True` |

### PA2-3 Tool contracts omit `ctx: Context` — FIXED

**Locations:** All six tool contracts (plan lines 225-450).

**Fix applied:** The plan now documents the `ctx: Context` convention (lines
225-229) and every tool handler signature accepts `ctx: Context` as the second
parameter, e.g. `async def seedance_create_task(input: SeedanceCreateTaskInput,
ctx: Context) -> SeedanceCreateTaskOutput:`.

### PA2-4 Inline-media helpers unnamed — FIXED

**Location:** `MCP Resources and Results` (plan line 510).

**Fix applied:** Line 510 now reads:

> an MCP image or audio content block only when below
> `MCP_INLINE_MEDIA_MAX_BYTES`, using FastMCP's `Image` and `Audio` helpers
> from `fastmcp.utilities.types` to auto-serialize to `ImageContent` /
> `AudioContent`;

### PA2-5 Resource binary MIME is underspecified — FIXED

**Location:** `MCP Resources and Results` (plan lines 469-489).

**Fix applied:** The resource handler now returns `ResourceResult` with
explicit `ResourceContent(content=..., mime_type=...)` instead of bare `bytes`:

```python
from fastmcp.resources import ResourceResult, ResourceContent

@mcp.resource("seed-media://artifacts/{artifact_id}")
async def get_artifact(artifact_id: str) -> ResourceResult:
    """Return persisted media by artifact ID with the correct MIME type."""
    artifact = await artifact_store.get(artifact_id, auth=ctx_auth)
    return ResourceResult(
        contents=[
            ResourceContent(
                content=artifact.data,
                mime_type=artifact.mime_type,
            )
        ],
        meta={"artifact_id": artifact_id, "media_type": artifact.media_type},
    )
```

Verified against FastMCP v3.x docs: `ResourceResult` accepts `contents` (str |
bytes | list[ResourceContent]) and `meta` (dict); `ResourceContent` accepts
`content`, `mime_type`, and `meta` (`docs/servers/resources.mdx`).

### PA2-6 Overstated automatic `.env` reading — FIXED

**Location:** `Configuration Contract` (plan line 634).

**Fix applied:** Line 634 now clarifies that FastMCP's built-in settings read
`.env` for their own keys, while the project's custom keys
(`BYTEPLUS_*`, `ARTIFACT_*`, etc.) must be loaded explicitly via a Pydantic
Settings model in `config/env.py`.

## Pass 2 — Optional polish (both done)

### OP-1 Add `respx` as a dev dependency — DONE

`respx` added to the Phase 1 `uv add --dev` line (plan line 701).

### OP-2 Show `fastmcp.json` contents explicitly — DONE

A `fastmcp.json` example block added to the Configuration Contract (plan lines
589-607).

## Pass 3 — Open findings (all fixed)

### PA3-1 `ToolAnnotations` import path — FIXED

**Location:** Plan line 232.

The plan imported `ToolAnnotations` from `fastmcp` top-level. The canonical
and documented path is `fastmcp.types`, verified in
`docs/development/v4-notes/change-register.mdx` and `docs/servers/tools.mdx`.

**Fix applied:** The import block now reads:

```python
from fastmcp import FastMCP, Context
from fastmcp.types import ToolAnnotations
```

### PA3-2 Resource handler references undefined `ctx_auth` — FIXED

**Location:** Plan lines 472-485.

The resource handler body used `auth=ctx_auth` but the function signature did
not declare `ctx: Context`, so `ctx_auth` was undefined.

**Fix applied:** The handler now accepts `ctx: Context` as the second parameter
and derives `auth` from it:

```python
@mcp.resource("seed-media://artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, ctx: Context) -> ResourceResult:
    """Return persisted media by artifact ID with the correct MIME type."""
    auth = derive_auth_from_context(ctx)
    artifact = await artifact_store.get(artifact_id, auth=auth)
    ...
```

## Pass 4 — Open findings

### PA4-1 Tool return type vs composite-result tension

**Locations:** Tool contracts (plan lines 282-288, 317-323, 364-370, 400-406,
423-429, 444-450) vs `MCP Resources and Results` (plan lines 509-514).

The six tool contracts declare Pydantic model return types (e.g.
`-> SeedAudioGenerateOutput`). FastMCP, when a tool returns a bare Pydantic
model, auto-serializes it into `structuredContent` plus a single JSON text
block — and nothing else. Verified in `docs/servers/tools.mdx`: returning a
`Person` dataclass yields exactly `content: [TextContent]` +
`structuredContent`.

However, the `MCP Resources and Results` section (lines 509-514) states that
every successful tool result returns **four** things simultaneously:

1. `structuredContent` conforming to its output schema;
2. a concise serialized JSON text block for older MCP clients;
3. an MCP image or audio content block (when below the inline limit);
4. a `resource_link` for all persisted artifacts.

Items 3 and 4 cannot be produced when the tool returns a bare Pydantic model.
To return structured content **and** inline media **and** resource links from a
single tool, the handler must return a `ToolResult` object with explicit
`content` (a list of content blocks) and `structured_content` (the output model
as a dict). Verified in `docs/servers/tools.mdx`:

```python
from fastmcp.tools import ToolResult
from mcp.types import TextContent, ImageContent

ToolResult(
    content=[
        TextContent(type="text", text="..."),
        ImageContent(type="image", data="...", mime_type="image/png"),
        # resource link / embedded resource as needed
    ],
    structured_content=output_model.model_dump(),
)
```

**Recommended fix:** The plan should clarify which tools return a bare
Pydantic model (items 1-2 only) versus which return `ToolResult` (all four
items). Concretely:

- Generation tools (`seed_audio_generate`, `seedream_generate_image`,
  `seedance_get_task` on success) that need inline media + resource links
  should return `ToolResult` with `structured_content` set to the output model
  dict.
- Read-only tools (`seedance_list_tasks`) and the cancel/delete tool can
  return the bare Pydantic model (or `None`), since they have no inline media.
- Update the return type annotations on the generation tools from
  `-> SomeOutputModel` to `-> ToolResult` and note that `structured_content`
  carries the output model.

**Severity:** Moderate. Not a correctness bug, but the implementer will hit an
ambiguity at Phase 3 when trying to satisfy the "four content types" claim
with a bare model return type. Resolving this in the plan avoids a redesign
during implementation.

## BytePlus API verification

All BytePlus API facts in the plan were cross-checked against the official
BytePlus documentation index (accessed 2026-07-20) and are accurate:

- **Base URL and authentication** (1298459, updated 2026-06-29) — region-scoped
  base URL + Bearer auth. Matches plan.
- **Seedance create / retrieve / list / cancel-delete** (1520757 / 1521309 /
  1521675 / 1521720) — four operations match exactly; state-dependent DELETE
  semantics (`queued` cancel, terminal delete, `running`/`cancelled` reject)
  are correctly modeled. Matches plan.
- **Seedream image generation API** (1541523) — request fields, model
  families, reference limits, and 24-hour URL lifetime match plan.
- **Seed Audio** (`byteplusvoice/seedaudio-01`, `audiopricing`) — the index
  groups these under the **"Seed Speech"** library, which validates the
  two-gateway design (Seed Speech `X-Api-Key` vs ModelArk Bearer). Matches plan.

Additional note: the index also lists a **3D generation API** (Hyper3D /
Hitem3d) under ModelArk. The plan correctly excludes it from MVP.

## Strengths (preserve)

- Two-gateway split is correct and well-justified.
- Model IDs treated as configuration (capability registry) is the right call
  given region/account scoping and the 5.0 Lite alias inconsistency.
- DELETE fetch-then-validate-then-delete with explicit `mode` is the correct
  safety design.
- No automatic replay of billable mutations, plus `ambiguousCompletion`
  flagging, is correct given undocumented provider idempotency.
- Persist outputs before 2h / 24h URL expiry; `stdio` default with stderr-only
  logging — both correct per MCP spec.
- Phase 0 (contract verification) as a gate before coding is excellent.
- Deferring Seedream streaming and experimental MCP Tasks until the spec
  stabilizes is a sound MVP boundary.

## Recommended action order

1. ~~Fix PA2-1 through PA2-6 + OP-1, OP-2~~ (all done).
2. ~~Fix PA3-1 (`ToolAnnotations` import from `fastmcp.types`).~~
3. ~~Fix PA3-2 (add `ctx: Context` to resource handler, define `auth`).~~
4. Fix PA4-1 (clarify `ToolResult` vs bare Pydantic model return for tools
   that need inline media + resource links).

PA4-1 should be resolved before Phase 3 (tool schemas and services) to avoid
a redesign during implementation.

## Sources

### FastMCP (verified via Context7 `/prefecthq/fastmcp`, accessed 2026-07-20)

- [FastMCP tools](https://gofastmcp.com/servers/tools) — `@mcp.tool` decorator,
  `ToolAnnotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`), structured output, `Image` / `Audio` content helpers,
  `ToolResult` with `content` (list of content blocks) and
  `structured_content` (dict matching output schema).
- [FastMCP resources](https://gofastmcp.com/servers/resources) — `@mcp.resource`
  decorator, resource templates, `ResourceResult` / `ResourceContent`,
  `ctx: Context` in resource functions, binary `blob` and `mime_type`.
- [Running your server](https://gofastmcp.com/deployment/running-server) —
  `stdio` default, `mcp.run(transport="http", host=..., port=...)` signature,
  `fastmcp run` CLI.
- [Project configuration](https://gofastmcp.com/deployment/server-configuration)
  — `fastmcp.json` declarative configuration with `uv` environment.
- [FastMCP settings](https://gofastmcp.com/more/settings) — built-in settings
  keys vs custom environment variables.
- [FastMCP types](https://gofastmcp.com/development/v4-notes/change-register)
  — `from fastmcp.types import ToolAnnotations` canonical import path.
- [Upgrading from MCP SDK](https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk)
  — `fastmcp.types` re-exports protocol types.

### BytePlus (verified via `byteplus-docs` skill index, accessed 2026-07-20)

- [ModelArk base URL and authentication](https://docs.byteplus.com/en/docs/ModelArk/1298459)
  — updated 2026-06-29.
- [Create a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1520757)
  — updated 2026-06-29.
- [Retrieve a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1521309)
  — updated 2026-06-22.
- [List video generation tasks](https://docs.byteplus.com/en/docs/ModelArk/1521675)
  — updated 2026-06-22.
- [Cancel or delete a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1521720)
  — updated 2026-06-22.
- [Image generation API](https://docs.byteplus.com/en/docs/ModelArk/1541523)
  — updated 2026-07-17.
- [Seed Audio 1.0 API reference](https://docs.byteplus.com/en/docs/byteplusvoice/seedaudio-01)
  — updated 2026-07-09.
- [Seed Audio 1.0 billing](https://docs.byteplus.com/en/docs/byteplusvoice/audiopricing)
  — updated 2026-07-14.
