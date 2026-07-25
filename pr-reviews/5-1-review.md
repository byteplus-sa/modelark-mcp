# PR #5 Review — Round 1: Speech-to-Text via BytePlus LAS ASR

- **Repository:** byteplus-sa/modelark-mcp
- **PR:** https://github.com/byteplus-sa/modelark-mcp/pull/5
- **Head:** `feat/speech-to-text` @ `4d18faf882d3bed505261681f481ec5b98c88618`
- **Base:** `main`
- **Reviewer:** Independent review agent (round 1)
- **Verdict:** **changes requested**

---

## Summary

This PR adds two STT tools (`speech_to_text_create_task`, `speech_to_text_get_result`)
backed by a new `las` provider gateway with a correctly-implemented bare-key
`Authorization` header. The design faithfully follows the existing submit/poll
pattern (mirroring Seedance) and the code is clean, typed, and well-tested for the
URL-input path.

The core provider integration is **correct** — I verified the auth header, request-ID
extraction (body, not headers), operator-version derivation, error normalization, and
MIME additions against the official BytePlus LAS ASR docs and the existing codebase
patterns. All 559 tests pass; `ruff` and `mypy` are clean.

The changes requested concern the **TOS upload path** inside the submit tool, which has
both an error-handling defect and missing planned test coverage. These are narrow (they
only affect Base64/file input with TOS configured; the URL-only common path is solid)
but should be fixed before merge.

## Findings

### 1. [Medium] TOS upload `ProviderError` escapes uncaught in `speech_to_text_create_task`

**Evidence**

`src/modelark_mcp/tools/speech_to_text_create_task.py`:

- Line 205: `audio_url = await _resolve_audio_url(input.audio, settings, ctx)` is called
  **before** the `try/except ProviderError` block that begins at line 231.
- `_resolve_audio_url` (lines 122-182) wraps the TOS upload in `try/finally` only
  (lines 149 / 179) -- there is **no `except ProviderError`**. The upload itself can
  raise `ProviderError` via `call_with_retry(lambda: gateway.upload_bytes(...))` (line 175)
  and `gateway.presign_get(...)` (line 178).
- Therefore a TOS failure propagates out of `_resolve_audio_url` and is **not caught**
  by the `except ProviderError` at line 239, which only scopes the LAS `submit` call.

I confirmed this empirically by patching `billed_provider_slot` + `TosGateway` to raise
a `ProviderError`:

```
CONFIRMED: ProviderError escapes _resolve_audio_url uncaught -> TOS_FAIL: upload failed
```

**Contrast with the established pattern.** `tools/media_upload.py` (the TOS upload
specialist this tool mirrors) wraps the entire `billed_provider_slot` + upload block:

```python
# media_upload.py:163-191
try:
    async with billed_provider_slot(ctx, provider="tos", ...):
        ...
        url = await gateway.presign_get(key=key)
except ProviderError as exc:            # caught and normalized
    await ctx.error(f"TOS upload failed: {exc.message}")
    return provider_error_result(exc)
finally:
    await gateway.close()
```

Every other provider call in the codebase (`seedance_create_task`, `seedance_get_task`,
the STT LAS submit/poll) normalizes `ProviderError` into a structured `ToolResult` via
`provider_error_result(exc)`. The STT TOS path is the only one that does not.

**Impact**

When a user submits Base64 or `file_path` audio with TOS configured and the TOS upload
fails (transient 5xx, connection error), the `ProviderError` propagates as an unhandled
exception instead of the structured error `ToolResult` used everywhere else. FastMCP
catches it, but the client receives a generic framework error rather than the provider,
code, and http_status detail embedded in the normalized error. The budget reservation
inside `billed_provider_slot` is still released correctly (the context manager handles
that), and there is no resource leak (the TOS gateway is closed in the `finally`, and the
LAS `service` is created later), so this is an error-quality / consistency defect, not
data corruption.

**Suggested fix**

Add a `try/except ProviderError` around the `_resolve_audio_url` call site that returns
`provider_error_result(exc)`, matching `media_upload`. For example:

```python
try:
    audio_url = await _resolve_audio_url(input.audio, settings, ctx)
except ProviderError as exc:
    await ctx.error(f"Speech-to-text audio upload failed: {exc.message}")
    return provider_error_result(exc)
```

**Suggested verification**

- Add an integration test that patches `TosGateway.upload_bytes` to raise a
  `ProviderError` and asserts the tool returns a `ToolResult` with `is_error=True`
  containing the TOS code/message (not an unhandled exception).

### 2. [Low] Two planned integration tests for the TOS upload path are missing

**Evidence**

`plans/PLAN_SPEECH_TO_TEXT.md` (lines 1098-1108) specifies:

```python
async def test_base64_input_with_tos(self, test_env, fake_ctx, temp_store, monkeypatch) -> None: ...
async def test_file_path_stdio_only(self, test_env, fake_ctx, monkeypatch) -> None: ...
```

A repository-wide search confirms neither test exists:

```
$ grep -rn 'test_base64_input_with_tos|test_file_path_stdio_only' tests/
NOT FOUND
```

`tests/integration/test_speech_to_text_create_task.py` implements 5 of the 7 planned
tests. The two omitted tests are exactly the ones that exercise `_resolve_audio_url`'s
TOS upload branch -- the most complex new code path and the path containing Finding 1.

**Impact**

The Base64->TOS->presigned-URL and file_path->TOS->presigned-URL code paths have zero
integration coverage. Combined with Finding 1, the unhandled-error path is both
defective and untested.

**Suggested fix**

Implement the two planned tests, mocking `TosGateway` to return a presigned URL (and
mocking `LasAsrService.submit` for the subsequent LAS call). Add a third test for the
TOS-upload-failure case described in Finding 1.

**Suggested verification**

```
uv run pytest tests/integration/test_speech_to_text_create_task.py -q
```

## Observations (no action required, documented for awareness)

### A. [Low] Operator override can silently mismatch between create and poll

`speech_to_text_create_task` (line 209) and `speech_to_text_get_result` (line 124) both
default `operator` to `settings.las_default_operator`. The ownership store records only
`task_id`, not the operator used at submit time. If a client submits with
`operator="las_asr"` (-> `v2`) but polls without specifying `operator`, the poll sends
`las_asr_pro`/`v1` for a task created under `las_asr`/`v2`. The plan's open questions
note the poll API requires matching `operator_id` + `operator_version`.

This is **documented** -- the `get_result` tool description says "Must match the submit
call" -- and the common case (default operator for both calls) works correctly. A
mismatch produces a caught `ProviderError` -> structured `ToolResult`, not silent
corruption. No change required; flagged as a usability footgun the author may wish to
harden later (e.g., persist the operator alongside the task, or validate at poll).

### B. STT cost estimate uses a fixed 60-second placeholder

`speech_to_text_create_task.py:228` passes `duration_seconds=60.0` unconditionally, so
every STT task is estimated at the same cost regardless of actual audio duration.
`COST_PER_STT_SECOND = 0.0006` is explicitly a placeholder (plan open questions,
line 1323). This is acknowledged and not a defect.

## Verification of the 10 attention areas

| # | Area | Result |
|---|------|--------|
| 1 | Auth header (bare `Authorization`, no Bearer) | OK. `client.py:45` `"Authorization": self._api_key`. Verified against official docs (`--header "Authorization: $LAS_API_KEY"`). Contract test `test_bare_authorization_header` asserts the header equals `"las-test-key"`. |
| 2 | Request ID from body (`metadata.request_id`) | OK. `asr.py:55` and `asr.py:87` extract `parsed.metadata.request_id`, not headers. `extract_request_id` (client.py:59) is a no-op fallback for `BaseHttpGateway` compliance. |
| 3 | Error normalization (`{"metadata": {"business_code", "error_msg", "request_id"}}`) | OK. `client.py:70-115` `normalize_error` parses the LAS envelope correctly, with a JSON-decode fallback and non-dict guards. |
| 4 | Operator version (`las_asr_pro`->`v1`, `las_asr`->`v2`) | OK. `asr.py:135-142`. Verified against docs (`las_asr_pro` example uses `v1`). |
| 5 | TOS upload path mirrors `media_upload.py` | PARTIAL: mirrors the upload mechanics but **omits the `except ProviderError`** -- see Finding 1. |
| 6 | `language` field removed | OK. No source references a `language` field; only plan docs note its intentional removal (line 584). Language is handled via `enable_lid`. |
| 7 | `Literal` types for `audio_format` / `operator` | OK. `create_task.py:64` and `:108`; `get_result.py:36`. Schema validation enforced by Pydantic. |
| 8 | Config validators reject invalid operator/resource | OK. `env.py:298-313`. Tests `test_invalid_operator_rejected` / `test_invalid_resource_rejected` confirm. |
| 9 | No artifact persistence for STT | OK. `get_result.py` returns text directly; no `ArtifactStore` / `copy_from_trusted_url` calls. Correct. |
| 10 | MIME additions (flac, mkv) | OK. `media_policy.py`: `audio/flac`, `audio/x-flac` in audio set; `video/x-matroska` in video set. `_FORMAT_TO_MIME` mapping matches the allowed sets. |

## Validation commands run

| Command | Result |
|---|---|
| `uv run pytest -q` | **559 passed** in 10.98s |
| `uv run pytest tests/integration/test_speech_to_text_*.py tests/contract/test_las_asr_adapter.py -q` | 30 passed |
| `uv run ruff check <new las + stt files>` | All checks passed |
| `uv run mypy <new las + stt files>` | Success: no issues found in 7 source files |
| `git diff main...feat/speech-to-text --stat` | 29 files, +3579/-18 |
| Empirical ProviderError-escape test (patched `billed_provider_slot` + `TosGateway`) | **CONFIRMED** uncaught escape from `_resolve_audio_url` |
| `grep -rn 'test_base64_input_with_tos|test_file_path_stdio_only' tests/` | NOT FOUND |
| Fetched official BytePlus LAS ASR docs (auth, operator, endpoints) | Matches implementation |

## Remaining risk / unanswered questions

1. **Finding 1** -- TOS error path should be hardened and tested before relying on
   Base64/file STT submission in production.
2. **LAS ASR pricing** -- `COST_PER_STT_SECOND` is a placeholder; verify against actual
   LAS pricing before shipping (acknowledged in the plan).
3. **`FAILED` task_status inference** -- `FAILED` is inferred from `business_code != "0"`
   + non-empty `error_msg`. The docs only show `PENDING`/`ACCEPTED`/`COMPLETED`
   explicitly; the failure-status value is inferred and unverified against a real API
   call (acknowledged in the plan's open questions).
4. **Operator-version stability** -- the `las_asr`->`v2` / `las_asr_pro`->`v1` mapping
   is hard-coded; a future LAS operator-version change would require a code update
   (acknowledged in the plan).
