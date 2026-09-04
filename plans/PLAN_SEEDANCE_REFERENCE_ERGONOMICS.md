---
title: Seedance Reference Ergonomics & Batch Presign
type: plan
status: in-progress
created: 2026-09-04
updated: 2026-09-04
tags: [seedance, media, presign, ergonomics, coercion]
related: [PLAN_MODELARK_SEED_MULTIMODAL_MCP.md]
---

# Seedance Reference Ergonomics & Batch Presign Implementation Plan

**Goal:** Reduce agent-facing friction and backend round-trips by (1) auto-coercing
plain-string and `{"url": ...}` reference inputs for Seedance tools, (2) adding a
batch presign tool, and (3) returning a tailored validation message for malformed
image references.

**Source Context:**
- User request: "MCP Server Updates — Improving developer/agent ergonomics and backend resilience."
- Docs/specs read: `AGENTS.md`, `docs/tools.md`, `docs/api-reference.md`, `docs/security.md`, `docs/use-cases.md`, `docs/s3-object-storage.md`, `docs/api-keys.md`, `.agents/skills/modelark-mcp/SKILL.md`.
- Code inspected: `src/modelark_mcp/tools/_seedance_shared.py`, `seedance_create_task.py`, `seedance_2_5_create_task.py`, `seedance_create_task_variations.py`, `seedance_2_5_create_task_variations.py`, `media_presign.py`, `media_upload.py`, `seed_understand.py`, `src/modelark_mcp/domain/media.py`, `domain/models.py`, `providers/object_storage.py`, `providers/tos/client.py`, `providers/s3/client.py`, `runtime.py`, `server.py`, `tools/_parallel.py`, `tools/_errors.py`, `security/url_policy.py`; tests `tests/unit/test_tool_validators.py`, `tests/unit/test_seedance_2_5_input.py`, `tests/integration/test_media_presign_tool.py`, `tests/integration/test_seedance_tool.py`, `tests/integration/test_mcp_conformance.py`, `tests/fixtures/fake_context.py`.

**Architecture Decision:** Auto-coercion is implemented as `@model_validator(mode="before")` class methods on the shared `SeedanceImageInput` / `SeedanceAudioInput` / `SeedanceVideoInput` models in `_seedance_shared.py`. Because every Seedance create/variations tool reuses these shared models, coercion is inherited everywhere for free with zero per-tool changes. The batch presign tool is a new handler that reuses the existing `presign_get` gateway protocol and the `object_key_ownership_store.require_owner` ledger, returning per-key results (partial failures captured inline) rather than all-or-nothing. Item 3 is folded into the coercion validator: an unrecognized dict shape raises a tailored `ValueError` showing the expected `SeedanceImageInput` JSON structure.

**Parallelization Summary:** The two source-level changes (coercion in `_seedance_shared.py`; batch presign in `media_presign.py` + a new `media_presign_batch.py`) have disjoint source write scopes. However, they share integration surfaces — `server.py` registration, `docs/**`, `.agents/skills/**`, and the conformance test — and are small. Implementation is done sequentially by the main agent to keep the shared integration coherent; no parallel worker lanes are proposed because the shared files dominate and the source edits are trivial.

```mermaid
flowchart LR
    subgraph Coercion["Auto-coercion (mode=before)"]
        A["images: [...]"] --> B{"str or {\"url\":...}?"}
        B -->|"str"| C["{\"kind\":\"url\",\"url\":v,\"role\":\"reference_image\"}"]
        B -->|"{\"url\":...}"| D["set kind=url, role=reference_image"]
        B -->|"unrecognized dict"| E["raise tailored ValueError with example shape"]
    end
    C --> F["MediaSource.validate_source (SSRF URL check)"]
    D --> F
    subgraph Batch["media_presign_batch"]
        G["object_keys[]"] --> H["validate each key"]
        H --> I["require_owner per key"]
        I --> J["gateway.presign_get per key"]
        J --> K["MediaPresignBatchOutput {items, succeeded, failed}"]
    end
    F --> L["seedance_create_task / seedance_2_5_create_task / variations"]
```

## File Ownership

| Path | Owner | Responsibility | Notes |
| --- | --- | --- | --- |
| `src/modelark_mcp/tools/_seedance_shared.py` | Main agent | Add `mode="before"` coercion validators to `SeedanceImageInput`, `SeedanceAudioInput`, `SeedanceVideoInput` | Shared by all Seedance tools |
| `src/modelark_mcp/tools/media_presign.py` | Main agent | Extract `validate_object_key` helper (reused by batch) | Keep existing `MediaPresignInput` behavior |
| `src/modelark_mcp/tools/media_presign_batch.py` | Main agent | New batch presign tool + input/output models | New file |
| `src/modelark_mcp/server.py` | Main agent | Register `media_presign_batch` under `has_object_storage`, scope `media:presign` | Registration only; field descriptions live in the input-model files |
| `tests/unit/test_seedance_input_coercion.py` | Main agent | New unit tests for coercion + tailored error | New file |
| `tests/integration/test_media_presign_batch_tool.py` | Main agent | New integration tests for batch presign | New file |
| `tests/integration/test_mcp_conformance.py` | Main agent | Add `media_presign_batch` to `test_all_tools_registered` | Single assertion set |
| `docs/tools.md`, `docs/api-reference.md`, `docs/security.md`, `docs/api-keys.md`, `docs/use-cases.md`, `docs/s3-object-storage.md`, `README.md` | Main agent | Document batch tool + auto-coercion | Keep docs in lockstep with shipped code |
| `.agents/skills/modelark-mcp/SKILL.md` | Main agent | Update presign pattern + tool tables + coercion notes | Canonical skill source |

## Implementation Tasks

### Task 1: Auto-coercion validators in `_seedance_shared.py`

**Files:** `src/modelark_mcp/tools/_seedance_shared.py`

**Depends on:** None

**Can run in parallel with:** Task 2 (disjoint source files), but keep sequential per Parallelization Summary.

- [ ] Add `@model_validator(mode="before")` to `SeedanceImageInput` that: (a) coerces a `str` to `{"kind": "url", "url": data, "role": "reference_image"}`; (b) for a `dict` with `"url"` present and `"kind"` absent, sets `kind="url"` and `setdefault("role", "reference_image")`; (c) for a `dict` that has neither `"url"` nor `"kind"` (including a dict with only `"data"` but no `"kind"`), raises a tailored `ValueError` whose message shows a **static** example `SeedanceImageInput` JSON shape and never echoes the caller's input value (which may contain a URL or other sensitive content).
- [ ] Add the same `mode="before"` validator to `SeedanceAudioInput` with `role="reference_audio"` (role already defaults to `reference_audio`; the validator still needs to fill `kind` for `{"url": ...}` and accept a plain string).
- [ ] Add a `mode="before"` validator to `SeedanceVideoInput` coercing a plain `str` to `{"url": data}` (its `kind`/`role` already default correctly).
- [ ] Update the `images` / `audios` / `videos` `Field(description=...)` strings in `seedance_create_task.py` and `seedance_2_5_create_task.py` to state that a plain URL string or `{"url": ...}` is accepted.

**Validation:** `uv run pytest tests/unit/test_seedance_input_coercion.py -q`

### Task 2: Batch presign tool

**Files:** `src/modelark_mcp/tools/media_presign.py`, `src/modelark_mcp/tools/media_presign_batch.py`, `src/modelark_mcp/server.py`

**Depends on:** None

**Can run in parallel with:** Task 1 (disjoint source files)

- [ ] In `media_presign.py`, extract a module-level `validate_object_key(v: str) -> str` that encodes the current `_OBJECT_KEY_PATTERN` checks (alphanumeric/`-`/`_`/`/`, no leading `/`/`-`, no `//`, no trailing `/`), and have `MediaPresignInput._validate_object_key` delegate to it.
- [ ] Create `media_presign_batch.py` with `MediaPresignBatchInput` (`object_keys: list[str]` min_length=1, `expires_in_seconds: int | None` 60–604800), `MediaPresignBatchItem` (`object_key`, `url: str | None`, `expires_at: str | None`, `error: str | None`, `code: str | None`), and `MediaPresignBatchOutput` (`items: list[MediaPresignBatchItem]`, `succeeded: int`, `failed: int`). Every field gets a `Field(description=...)`. `code` carries a machine-readable error code (`"INVALID_KEY"`, `"NOT_OWNED"`, or the provider `ProviderError.code`) mirroring `VariationError.code`; `error` carries the human-readable message. This output shape deliberately does NOT reuse `VariationSummary`/`VariationResult`, whose `index`/`seed`/`artifact`/`task_id` semantics do not fit object keys.
- [ ] Implement `media_presign_batch(input, ctx)` handler: guard `has_object_storage`, build `make_object_storage_gateway`, wrap the loop in one `billed_provider_slot(provider=backend, product="presign", estimated_cost_usd=0.0)`; per key call `validate_object_key`, then `object_key_ownership_store.require_owner(key, principal)`, then `call_with_retry(lambda: gateway.presign_get(...))`; capture `ValueError`/`PermissionError`/`ProviderError` per key into `error` (increment `failed`), else append URL/expiry (increment `succeeded`). `finally: await gateway.close()`.
- [ ] Set `TOOL_ANNOTATIONS` to match `media_presign` (`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`).
- [ ] Register `media_presign_batch` in `server.py` under `settings.has_object_storage` with `auth=component_auth(settings, "media:presign")` and `output_schema=MediaPresignBatchOutput.model_json_schema()`.

**Validation:** `uv run pytest tests/integration/test_media_presign_batch_tool.py -q`

### Task 3: Tests

**Files:** `tests/unit/test_seedance_input_coercion.py`, `tests/integration/test_media_presign_batch_tool.py`, `tests/integration/test_mcp_conformance.py`

**Depends on:** Tasks 1, 2

- [ ] Unit tests (coercion): plain string image → `kind="url"`, `url`, `role="reference_image"`; `{"url": ...}` → `kind="url"`, `role="reference_image"`; plain string audio → `kind="url"`, `role="reference_audio"`; plain string video → `url` set; dict missing `url`/`data`/`kind` raises `ValidationError` whose message contains the example JSON hint; a valid `{"kind":"base64","data":...,"mime_type":"image/png"}` still passes (no `role` forced).
- [ ] Integration tests (batch): multi-key success returns per-key URLs; one malformed key among valid keys yields partial success (`succeeded`/`failed` counts correct); unknown key for a remote principal fails per-key with `PermissionError` message captured inline; custom `expires_in_seconds` forwarded; missing object-storage config raises `ValueError`.
- [ ] Add `"media_presign_batch"` to the expected tool set in `test_mcp_conformance.py::test_all_tools_registered`.

**Validation:** `uv run pytest tests/unit/test_seedance_input_coercion.py tests/integration/test_media_presign_batch_tool.py tests/integration/test_mcp_conformance.py -q`

### Task 4: Docs and skill updates

**Files:** `docs/tools.md`, `docs/api-reference.md`, `docs/security.md`, `docs/api-keys.md`, `docs/use-cases.md`, `docs/s3-object-storage.md`, `README.md`, `.agents/skills/modelark-mcp/SKILL.md`

**Depends on:** Tasks 1, 2

- [ ] `docs/tools.md`: add a `## media_presign_batch` section (input/output tables); add a short note under `seedance_create_task` / `seedance_2_5_create_task` that `images`/`audios`/`videos` accept plain URL strings or `{"url": ...}`.
- [ ] `docs/api-reference.md`: add `media_presign_batch` as #12 in the Tool Inventory table, the Tool Annotations table, and a new `## 12. media_presign_batch` section mirroring the `media_presign` section. This shifts **every** subsequent inventory row (12→13 … 30→31), every annotations row, and every `## N.` section heading by one — renumber all of them, not just the prose sections, and keep each `## N.` heading in sync with its inventory row number.
- [ ] `docs/security.md`: add `media_presign_batch` to the `media:presign` scope row and mention it in the object-storage credentials paragraph.
- [ ] `docs/api-keys.md`, `docs/use-cases.md`: mention the batch tool in the presign workflow notes.
- [ ] `docs/s3-object-storage.md`: add a `media_presign_batch` row to its Tools table (the table at the bottom enumerates `media_upload`/`media_presign`), update the JWT-scope note to include the batch tool, and mention it in the "Re-presigning existing objects" prose.
- [ ] `.agents/skills/modelark-mcp/SKILL.md`: update the "Batch presign" step to reference `media_presign_batch`; add it to the tool list/table and the `media_presign` reference; note auto-coercion in the Seedance reference examples.
- [ ] `README.md`: update the tool inventory if it enumerates tools.

**Validation:** `uv run ruff format src tests && uv run ruff check src tests`

### Task 5: Full validation

**Depends on:** Tasks 3, 4

- [ ] `uv run pytest --cov=modelark_mcp --cov-report=term-missing -q` (must stay ≥85% coverage).
- [ ] `uv run ruff check src tests scripts && uv run ruff format --check src tests scripts`.
- [ ] `uv run mypy src`.

## Parallel Subagent Execution Plan

No parallel worker lanes are proposed: the source changes are small and share integration files (`server.py`, `docs/**`, `.agents/skills/**`, conformance test). Implementation is sequential, owned by the main agent. (If parallelism were forced, only Task 1 and Task 2 have disjoint source write scopes; `server.py`, docs, and tests would still be sequenced under the main agent.)

**Implementation handoff:** The main agent will recheck the worktree state before editing, keep all edits on a dedicated feature branch, run validation after each task, and own final integration and reporting.

## Validation

- `uv run pytest --cov=modelark_mcp --cov-report=term-missing`: all pass, coverage ≥85%.
- `uv run ruff check src tests scripts`: no findings.
- `uv run ruff format --check src tests scripts`: no diffs.
- `uv run mypy src`: no errors.

## Documentation And Follow-Up

- Docs/specs to update: as listed in Task 4. A durable note on the auto-coercion contract may later be promoted into a spec, but the immediate change is small enough to live in tool docstrings + `docs/`.
- Known risks or non-blocking follow-up:
  - Forcing `role="reference_image"` on coerced image references changes the prior `None` (provider-auto) default, and the plain-string/`{"url":...}` convenience paths cannot express `first_frame`/`last_frame` (callers needing those roles must pass a full dict with an explicit `kind` and `role`). This matches the explicit request; documented in tool descriptions so the limitation is visible to clients.
  - `media_presign_batch` presigns keys sequentially within one MCP call (single round-trip goal is met); switching to `asyncio.gather` for in-call parallelism is a possible later optimization, not required now.
