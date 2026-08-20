# PR #35 Review — Round 1

- **PR:** https://github.com/byteplus-sa/modelark-mcp/pull/35
- **Repository:** byteplus-sa/modelark-mcp
- **Base:** `main` · **Head:** `feat/vod-audio-separation`
- **Exact head SHA reviewed:** `a1d1acc356c837df9f4d4ea6a2fa51ab0bf7b4b8` (verified against `git rev-parse HEAD` in the clean worktree and `origin/feat/vod-audio-separation`)
- **Round:** 1
- **Review mode:** read-only, exact-head. No source edits, no commits, no public comments. CI was not polled (supervisor handles it).

## Verdict

**changes requested**

The HMAC-SHA256 signing implementation is correct against the documented
BytePlus OpenAPI v4 algorithm, DTO aliasing/validation is sound, secret-key
handling is solid, and error normalization largely matches repo conventions.
One medium finding (playback-URL construction does not percent-encode the
`FileName` path segment) plus several low-severity robustness gaps should be
addressed before merge. No blockers.

## Scope inspected

- `src/modelark_mcp/providers/vod/{client,schemas,audio_separation,__init__}.py`
- `src/modelark_mcp/tools/vod_separate_audio.py`, `vod_get_audio_separation.py`
- `src/modelark_mcp/config/env.py`, `domain/errors.py`, `runtime.py`, `server.py`
- `src/modelark_mcp/providers/base.py`, `providers/retry.py`, `tools/_errors.py`
- Tests: `tests/contract/test_vod_openapi_signing.py`,
  `tests/contract/test_vod_audio_separation_adapter.py`,
  `tests/integration/test_vod_audio_separation_tool.py`,
  `tests/integration/test_mcp_conformance.py`, `tests/integration/conftest.py`
- Docs/spec/plan: `README.md`, `docs/*`, `.env.example`,
  `.agents/skills/modelark-mcp/SKILL.md`,
  `plans/PLAN_BYTEPLUS_VOD_AUDIO_SEPARATION.md`,
  `specs/SPEC_VOD_OPENAPI_PROVIDER_CONTRACT.md`, `.secrets.baseline`

## Signing algorithm — verified correct

Cross-checked `client.py` against the live BytePlus doc
`https://docs.byteplus.com/en/docs/byteplus-platform/reference-how-to-calculate-a-signature`
(fetched 2026-08-20). The implementation matches the documented algorithm
point-for-point:

- `CanonicalRequest = METHOD \n / \n CanonicalQueryString \n CanonicalHeaders \n SignedHeaders \n HexEncode(Hash(payload))` — `client.py:120-129`
- RFC3986 query encoding (`quote(value, safe="-_.~")`, ASCII-sorted keys) — `client.py:43-51`
- Lowercased, ASCII-sorted, trimmed canonical headers — `client.py:116-118`
- `X-Date` `YYYYMMDDTHHMMSSZ`; `X-Content-Sha256` = hex SHA-256 of body (empty for GET) — `client.py:103-115`
- Credential scope `{shortdate}/{region}/vod/request` — `client.py:130`
- Signing key `HMAC(HMAC(HMAC(HMAC(SK, date), region), "vod"), "request")` — `client.py:88-93`
- Authorization header format — `client.py:145-148`

Verified via httpx that the explicit `host` header is sent on the wire as
signed, so signature and request agree for the default base URL.

## Findings

### 1. (Medium) Playback URL does not percent-encode the `FileName` path segment

**Evidence:** `src/modelark_mcp/tools/vod_get_audio_separation.py:109-128`
(`_build_track_url`). The `file_name` is interpolated raw into
`urlsplit(f"https://{domain}/{file_name}")`.

**Trigger/execution path:** A poll result whose Voice/Background `FileName`
contains reserved characters. Demonstrated locally:

```
'a?b.aac' -> 'https://play.example.com/a?b.aac'   # filename becomes query
'a#b.aac' -> 'https://play.example.com/a#b.aac'   # filename becomes fragment
'a b.aac' -> 'https://play.example.com/a b.aac'   # literal space in URL
'a&b.aac' -> 'https://play.example.com/a&b.aac'
```

`HttpsUrl` (pydantic `AnyUrl`) accepts all of these, so the invalid/ambiguous
URL is returned to the client as-is.

**Impact:** The `url` field in `VodAudioTrack` can be a semantically wrong or
malformed URL for any FileName containing `?`, `#`, `&`, ` `, etc. Provider
FileNames are currently hash-based (`hash_audiospeech.aac`), so likelihood is
low, but the code promises `https://{domain}/{FileName}` and does not deliver
it for arbitrary storage keys. No server-side SSRF (the URL is never fetched),
so this is correctness, not a direct exploit.

**Suggested fix:** Percent-encode the path component before building the URL,
e.g. `from urllib.parse import quote` and
`path = quote(file_name, safe="/")` then `urlsplit(f"https://{domain}/{path}")`.
Optionally add a unit test for `?`/`#`/space filenames.

**Suggested verification:** Add cases to
`tests/integration/test_vod_audio_separation_tool.py` (or a new unit test for
`_build_track_url`) asserting a FileName of `"a?b.aac"` produces
`https://play.example.com/a%3Fb.aac`.

**Prompt for AI Agents:**
- Files: `src/modelark_mcp/tools/vod_get_audio_separation.py`,
  `tests/integration/test_vod_audio_separation_tool.py`
- Change: In `_build_track_url`, wrap the file name with
  `urllib.parse.quote(file_name, safe="/")` before building the URL string;
  import `quote` alongside `urlsplit`. Add tests covering FileNames containing
  `?`, `#`, `&`, and a space.
- Constraints: No new dependencies. Keep the existing bare-hostname domain
  validation and the `HttpsUrl` return type. Do not change the domain
  validation behavior.
- Acceptance criteria: `_build_track_url("play.example.com", "a?b.aac")`
  returns `https://play.example.com/a%3Fb.aac`; existing playback-URL tests
  still pass.
- Verify: `uv run pytest tests/integration/test_vod_audio_separation_tool.py -q`
  and `uv run ruff check src tests`.

### 2. (Low) `playback_domain` validation deferred to the success path and raises a bare `ValueError`

**Evidence:** `src/modelark_mcp/tools/vod_get_audio_separation.py:147`
(domain resolved from input/settings) and `:160-172` (validation only inside
`_build_track_url`, which runs only when `task.status == "succeeded"`). The
input model `VodGetAudioSeparationInput.playback_domain` (`:30-36`) has no
validator.

**Trigger/execution path:** A client passes an invalid `playback_domain` (e.g.
`https://play.example.com`) while the task is still `processing` or `failed`:
the invalid input is silently accepted and never rejected. When the task is
`succeeded`, the bare `ValueError` from `_build_track_url` is not caught by the
`except ProviderError` handler (`:152-154`), so it escapes as an unstructured
handler exception rather than the normalized `ToolResult` error used
everywhere else.

**Impact:** Inconsistent input validation (fail-late instead of fail-fast) and
an inconsistent error surface for invalid input. The integration test
`test_poll_rejects_invalid_playback_domain` codifies the `ValueError`, so this
is partly intentional, but it should be a model-boundary validation.

**Suggested fix:** Add a `field_validator` to
`VodGetAudioSeparationInput.playback_domain` (mirroring the
`BYTEPLUS_VOD_PLAYBACK_DOMAIN` validator in `config/env.py`) so invalid domains
are rejected at input validation with a structured error. Keep
`_build_track_url` as a defense-in-depth check.

**Suggested verification:** Update
`tests/integration/test_vod_audio_separation_tool.py:240-254` to assert the
input model raises `ValidationError` (or the tool returns an error `ToolResult`)
for an invalid domain, independent of task status.

**Prompt for AI Agents:**
- Files: `src/modelark_mcp/tools/vod_get_audio_separation.py`,
  `tests/integration/test_vod_audio_separation_tool.py`
- Change: Add a Pydantic `field_validator` on
  `VodGetAudioSeparationInput.playback_domain` that applies the same
  bare-hostname checks as `config/env.py:validate_playback_domain`; import
  `field_validator` from `pydantic`. Update the existing
  `test_poll_rejects_invalid_playback_domain` to assert the validation fires at
  input-model validation (or returns an error `ToolResult`) rather than relying
  on a raw `ValueError` from the success path.
- Constraints: No new dependencies. Do not weaken existing domain validation.
  Keep `_build_track_url` behavior for configured settings domains.
- Acceptance criteria: Invalid `playback_domain` values are rejected before the
  provider call regardless of task status; the error is a structured MCP error.
- Verify: `uv run pytest tests/integration/test_vod_audio_separation_tool.py -q`
  and `uv run ruff check src tests`.

### 3. (Low) `normalize_error` fails open on a malformed `ResponseMetadata` envelope

**Evidence:** `src/modelark_mcp/providers/vod/client.py:194-204`. Inside the
`else` branch (valid JSON, `isinstance(parsed, dict)`),
`VodResponseMetadata.model_validate(parsed.get("ResponseMetadata") or {})` is
not guarded. If `ResponseMetadata` is a non-dict (list, string, number), the
call raises `pydantic.ValidationError`, which propagates out of
`normalize_error` instead of returning a normalized `ProviderError`.

**Trigger/execution path:** Any non-2xx response whose body is valid JSON but
whose `ResponseMetadata` is not an object (e.g. `{"ResponseMetadata": []}`).
The caller (`audio_separation.py:59,128`) raises the resulting `ValidationError`
instead of a `ProviderError`, so the tool's `except ProviderError` handler does
not convert it and the client receives an unstructured error.

**Impact:** Fail-open error normalization: the HTTP error still surfaces, but
without the normalized provider code/message/request-id/retryable metadata.
No retry or mutation risk (the non-2xx path already aborts), but the error
contract degrades on malformed input.

**Suggested fix:** Wrap the `model_validate` in a try/except
(`pydantic.ValidationError`) and fall back to `VodResponseMetadata()` (i.e.
`code = f"HTTP_{status}"`, generic fallback message), mirroring the defensive
style used in `audio_separation.py:61-79`.

**Suggested verification:** Add a contract test in
`tests/contract/test_vod_audio_separation_adapter.py` that returns a non-2xx
with `{"ResponseMetadata": []}` and asserts a `ProviderError` with
`code == "HTTP_4xx"` is raised (not `ValidationError`).

**Prompt for AI Agents:**
- Files: `src/modelark_mcp/providers/vod/client.py`,
  `tests/contract/test_vod_audio_separation_adapter.py`
- Change: In `VodOpenApiGateway.normalize_error`, guard the
  `VodResponseMetadata.model_validate(...)` call with a try/except that falls
  back to an empty metadata object on `pydantic.ValidationError` so the
  function always returns a normalized `ProviderError`.
- Constraints: No new dependencies. Preserve existing successful-parsing
  behavior and the `code = code or f"HTTP_{status}"` fallback.
- Acceptance criteria: A non-2xx response with a non-dict `ResponseMetadata`
  raises `ProviderError` (not `ValidationError`) with a normalized HTTP code.
- Verify: `uv run pytest tests/contract/test_vod_audio_separation_adapter.py -q`
  and `uv run mypy src`.

### 4. (Low) Signed `host` header drops the port for non-default-port base URLs

**Evidence:** `src/modelark_mcp/providers/vod/client.py:108` —
`host = httpx.URL(self._base_url).host or "vod.byteplusapi.com"`.
`httpx.URL(...).host` excludes the port. The settings URL validator
(`config/env.py:validate_provider_url`) does not forbid a port.

**Trigger/execution path:** `BYTEPLUS_VOD_BASE_URL=https://vod.byteplusapi.com:8443`.
The signed `host` header becomes `vod.byteplusapi.com` (no port), while the
actual HTTP request connects to port 8443. The signature is internally
self-consistent (the explicit header is sent as signed), but the Host header is
invalid per RFC 7230 for a non-default port and BytePlus may reject the request
or route it incorrectly.

**Impact:** Signing breaks for any configured non-default port. The default
configuration (port 443) is unaffected.

**Suggested fix:** Include the port in the signed host header when the base URL
has a non-default port (e.g.
`f"{host}:{port}" if port not in (None, 443) else host`), or reject ports in
`validate_provider_url` for the VOD base URL.

**Suggested verification:** Add a unit test for `_authorization_headers` with a
base URL including `:8443` and assert the host header includes `:8443`.

**Prompt for AI Agents:**
- Files: `src/modelark_mcp/providers/vod/client.py`,
  `tests/contract/test_vod_openapi_signing.py`
- Change: In `VodOpenApiGateway._authorization_headers`, compute the host header
  value including the port when `httpx.URL(self._base_url).port` is present and
  not 443. Add a test case for a base URL with a non-default port.
- Constraints: No new dependencies. Keep default behavior identical for
  `https://vod.byteplusapi.com`.
- Acceptance criteria: The signed host header matches the effective Host header
  for both default and non-default ports.
- Verify: `uv run pytest tests/contract/test_vod_openapi_signing.py -q`.

### 5. (Low / consistency note) Read operations are normalized as ambiguous

**Evidence:** `src/modelark_mcp/providers/vod/client.py:208`
(`ambiguous = status >= 500` applies to both POST and GET) and
`src/modelark_mcp/providers/vod/audio_separation.py:114-125` (GET transport
timeout raised via `normalize_ambiguous_transport_error`, i.e.
`ambiguous_completion=True`).

**Trigger/execution path:** A `GetExecution` (read) 5xx or timeout is reported
to the client with `ambiguous_completion=True`, which semantically means "the
mutation may have happened but we cannot tell". For a read, completion of the
original separation task is not in question; the poll simply failed and can be
retried.

**Impact:** Misleading error metadata only. It does not affect retry behavior
(`retryable` is already `False` for 5xx, and `call_with_retry` requires
`retryable and not ambiguous_completion`). This matches the existing
`vod_mediakit` provider pattern exactly, so it is a pre-existing repo
convention rather than a regression.

**Suggested fix:** Optional: distinguish read vs mutation in `normalize_error`
(only mark `ambiguous_completion` for the submit operation). Not required to
merge; flagging for the record.

## Validation run (this round)

| Command | Result |
|---|---|
| `git rev-parse HEAD` | `a1d1acc356c837df9f4d4ea6a2fa51ab0bf7b4b8` (matches) |
| `.venv/bin/python -m pytest tests/contract/test_vod_openapi_signing.py tests/contract/test_vod_audio_separation_adapter.py tests/integration/test_vod_audio_separation_tool.py tests/integration/test_mcp_conformance.py -q` | 72 passed |
| `.venv/bin/python -m ruff check src/modelark_mcp/providers/vod src/modelark_mcp/tools/vod_separate_audio.py src/modelark_mcp/tools/vod_get_audio_separation.py src/modelark_mcp/config/env.py` | All checks passed |
| `.venv/bin/python -m mypy src/modelark_mcp/providers/vod src/modelark_mcp/tools/vod_separate_audio.py src/modelark_mcp/tools/vod_get_audio_separation.py` | Success: no issues found |
| httpx probe: explicit `host` header on the wire | Sent as provided (matches signature) |
| URL probe: `_build_track_url`-equivalent with reserved-char FileNames | Confirmed finding #1 |

Supervisor-reported (clean worktree, not re-run here): `uv run ruff check src
tests`, `uv run ruff format --check src tests`, `uv run mypy src` all clean;
`uv run pytest -q` 888 passed.

## Earlier-round findings inspected

None (round 1).

## Residual risks / questions

- **Unverified provider contract points** (already disclosed in the spec): the
  full `GetExecution` `Status` enum beyond `Success`/failure labels, and the
  `Input.DirectUrl` object shape, are confirmed indirectly rather than from a
  rendered `StartExecution` reference page. The code fails closed on unknown
  statuses, so this is a documentation-vs-reality risk, not a code risk.
- **No live call validation.** The PR has no end-to-end call against
  `vod.byteplusapi.com` with real credentials; signing correctness is pinned
  only by offline fixtures. A one-time live smoke test (submit a tiny sample,
  poll, download one track) is recommended before broad rollout.
- **Output URL hotlink protection** (`auth_key`) is not implemented (noted in
  the spec). Clients with URL signing enabled on the playback domain will get
  URLs that 403 until they sign them.
- **Duplicate bare-hostname validation logic** between
  `config/env.py:validate_playback_domain` and
  `tools/vod_get_audio_separation.py:_build_track_url` — minor DRY drift risk;
  a shared helper would prevent the two checks from diverging (they already
  differ slightly: the tool also rejects spaces).

## Disclosure

Reviewed with the help of an AI Agent. Please validate recommendations.
