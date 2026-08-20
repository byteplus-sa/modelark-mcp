---
title: Migrate VOD Audio Separation to AI MediaKit Bearer Surface
type: plan
status: shipped
created: 2026-08-20
updated: 2026-08-20
tags:
  - byteplus-vod
  - ai-mediakit
  - audio-separation
  - migration
source:
  - https://docs.byteplus.com/en/docs/byteplus-vod/docs-voice-background-audio-separation
  - https://docs.byteplus.com/en/docs/byteplus-vod/ai-mediakit-create-a-voice-separation-task
  - https://docs.byteplus.com/en/docs/byteplus-vod/ai-mediakit-get-task-details
related:
  - plans/PLAN_BYTEPLUS_VOD_AUDIO_SEPARATION.md
  - specs/SPEC_VOD_MEDIAKIT_PROVIDER_CONTRACT.md
  - specs/SPEC_VOD_OPENAPI_PROVIDER_CONTRACT.md
---

<!-- markdownlint-disable MD013 MD025 -->

# Migrate VOD Audio Separation to the AI MediaKit Bearer Surface

**Goal:** Replace the AK/SK-signed VOD OpenAPI `StartExecution`/`GetExecution`
`AudioExtract` implementation of `vod_separate_audio` /
`vod_get_audio_separation` with the Bearer-authenticated AI MediaKit
`POST /api/v1/tools/separate-voice` + `GET /api/v1/tasks/{task_id}` surface.
The MediaKit surface is the one documented under "AI MediaKit Voice and
Background Audio Separation" and uses the same `BYTEPLUS_VOD_MEDIAKIT_API_KEY`
as `vod_enhance_video` / `vod_transcode_video`.

## Scope decisions (confirmed with owner)

1. **Replace entirely.** Remove the OpenAPI AK/SK audio-separation path: the
   `providers/vod/` package, `BYTEPLUS_VOD_ACCESS_KEY_ID` /
   `BYTEPLUS_VOD_SECRET_ACCESS_KEY` / `BYTEPLUS_VOD_BASE_URL` /
   `BYTEPLUS_VOD_REGION` / `BYTEPLUS_VOD_PLAYBACK_DOMAIN` config, `has_vod`,
   the `"byteplus-vod"` provider name, and the `"vod"` limiter key.
2. **Full documented range.** Expose `scene` (`Audio` default, `Music`,
   `Drama`, `Narrate`) and `output_format` (`aac` default, `mp3`, `wav`,
   `m4a`, `flac`). Two-way scenes return voice + background; three-way scenes
   return voice + music + sfx.
3. **Mirror transcode persistence.** Return provider 24h URLs directly and
   best-effort persist each track as a durable artifact, exactly like
   `vod_get_transcode_task`.
4. **Keep tool names.** `vod_separate_audio` / `vod_get_audio_separation` keep
   their names; their schemas change (public URL input, `task_id` polling,
   `voice`/`background`/`music`/`sfx` URL output). This is a breaking schema
   change for existing callers.

## Provider contract (documented)

| Item | Value |
| --- | --- |
| Submit | `POST /api/v1/tools/separate-voice` with `Authorization: Bearer` |
| Submit body | `{ "audio_url" \| "video_url", "scene"?, "output_format"? }` |
| Submit response | `{ success, task_id, request_id }` |
| Poll | `GET /api/v1/tasks/{task_id}` |
| Poll statuses | `running` → processing, `completed` → succeeded, `failed` → failed; others `INVALID_RESPONSE` |
| Completed result | `{ voice_audio_url, background_audio_url, duration }` (2-way) or `{ voice_audio_url, music_audio_url, sfx_audio_url, duration }` (3-way) |
| Output lifetime | URLs valid 24 hours |

`scene`/`output_format` are top-level request fields (not nested). Output
track URLs are direct HTTPS URLs; there is no playback-domain construction.

## Implementation

### `providers/vod_mediakit/schemas.py` (add)

```python
class VodMediaKitSeparateVoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    audio_url: HttpsUrl | None = None
    video_url: HttpsUrl | None = None
    scene: Literal["Audio", "Music", "Drama", "Narrate"] = "Audio"
    output_format: Literal["aac", "mp3", "wav", "m4a", "flac"] = "aac"

    @model_validator(mode="after")
    def require_exactly_one_source(self):
        if (self.audio_url is None) == (self.video_url is None):
            raise ValueError("exactly one of audio_url or video_url is required")
        return self
```

```python
class VodMediaKitSeparateVoiceTaskResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    voice_audio_url: HttpsUrl | None = None
    background_audio_url: HttpsUrl | None = None
    music_audio_url: HttpsUrl | None = None
    sfx_audio_url: HttpsUrl | None = None
    duration: float | None = Field(default=None, ge=0)

class VodMediaKitSeparateVoiceTaskResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    success: Literal[True]
    task_id: str = Field(min_length=1)
    task_type: str | None = None
    status: str = Field(min_length=1)
    result: VodMediaKitSeparateVoiceTaskResult | None = None
    error: VodMediaKitProviderErrorDetail | None = None
    request_id: str | None = None
    expires_at: str | int | None = None
    created_at: str | int | None = None
    finished_at: str | int | None = None

class SeparateVoiceSubmission(BaseModel):  # accepted
    status: Literal["accepted"]
    request_id: str | None = None
    provider_log_id: str | None = None
    task_id: str = Field(min_length=1)

class SeparateVoiceTask(BaseModel):  # normalized
    task_id: str
    status: Literal["processing", "succeeded", "failed"]
    provider_status: str | None = None
    request_id: str | None = None
    voice_url: HttpsUrl | None = None
    background_url: HttpsUrl | None = None
    music_url: HttpsUrl | None = None
    sfx_url: HttpsUrl | None = None
    duration_seconds: float | None = None
    created_at: str | None = None
    finished_at: str | None = None
    source_expires_at: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    # validators mirror TranscodeTask
```

### `providers/vod_mediakit/separate_voice.py` (new)

`VodMediaKitSeparateVoiceService` reusing `VodMediaKitGateway` and the
`_normalize_timestamp` / `_sanitize_task_error` helpers from `transcode.py`:

- `submit(request) -> SeparateVoiceSubmission` — POST
  `/tools/separate-voice`; never retries ambiguous mutation; validates
  `VodMediaKitAcceptedResponse`.
- `get(task_id) -> SeparateVoiceTask` — GET `/tasks/{task_id}`; maps
  `running`→processing, `completed`→succeeded (requires at least one track
  URL), `failed`→failed, else `INVALID_RESPONSE`.
- `close()`.

### `tools/vod_separate_audio.py` (rewrite)

```python
class VodSeparateAudioInput(BaseModel):
    audio_url: HttpsUrl | None = None
    video_url: HttpsUrl | None = None
    scene: Literal["Audio", "Music", "Drama", "Narrate"] = "Audio"
    output_format: Literal["aac", "mp3", "wav", "m4a", "flac"] = "aac"
    # model_validator: exactly one source URL
```

Gates on `settings.has_vod_mediakit` (Bearer key), validates source URL via
`validate_url`, limiter `"vod-mediakit"`, ownership `"vod-mediakit"`. Output:
`provider="byteplus-vod-mediakit"`, `status="accepted"`, `task_id`,
`request_id`, `provider_log_id`, `recommended_poll_after_ms=3000`.

### `tools/vod_get_audio_separation.py` (rewrite)

```python
class VodGetAudioSeparationInput(BaseModel):
    task_id: str
    persist_output: bool = True

class VodAudioTrack(BaseModel):          # per-track durable artifact + source URL
    artifact: ArtifactRef | None
    source_url: HttpsUrl | None
    source_expires_at: str | None
    persistence: Literal["not_applicable", "not_requested", "persisted", "failed"]
    persistence_issue: VodArtifactPersistenceIssue | None

class VodAudioSeparationTaskOutput(BaseModel):
    provider: Literal["byteplus-vod-mediakit"]
    task_id: str
    status: Literal["processing", "succeeded", "failed"]
    provider_status, request_id, duration_seconds, created_at, finished_at
    voice: VodAudioTrack | None
    background: VodAudioTrack | None
    music: VodAudioTrack | None
    sfx: VodAudioTrack | None
    error: VodAudioSeparationFailure | None
```

Persistence mirrors `vod_get_transcode_task._persist_output`, but iterates the
present track URLs and stores each under its own cache key, with `MediaType.AUDIO`
and MIME derived from the requested/result `output_format` (provider returns
AAC by default; the poll response does not include MIME, so persist with
`mime_type=None` when unknown and let the store infer, or map `aac` →
`audio/aac`). Ownership/limiter use `"vod-mediakit"`.

## Deletions

- `src/modelark_mcp/providers/vod/` (whole package: `client.py`, `schemas.py`,
  `audio_separation.py`, `__init__.py`).
- `tests/contract/test_vod_openapi_signing.py`.
- `tests/contract/test_vod_audio_separation_adapter.py`.

## Edits

| Path | Change |
| --- | --- |
| `src/modelark_mcp/config/env.py` | Remove `vod_access_key_id`, `vod_secret_access_key`, `vod_base_url`, `vod_region`, `vod_playback_domain`, `has_vod`, URL/playback validators, `validate()` checks |
| `src/modelark_mcp/domain/errors.py` | Remove `"byteplus-vod"` from `ProviderName` |
| `src/modelark_mcp/runtime.py` | Remove `"vod"` from `ProviderKey` and limiter dict |
| `src/modelark_mcp/server.py` | Register separation tools under `has_vod_mediakit`; update instructions, health resource, ready probe |
| `.env.example` | Remove OpenAPI credential/base URL/playback lines |
| `tests/integration/conftest.py` | Remove OpenAPI env vars |
| `tests/integration/test_mcp_conformance.py` | Update expected tool set, annotations, schema assertions |
| `tests/integration/test_vod_audio_separation_tool.py` | Rewrite for MediaKit surface |
| `tests/contract/test_vod_mediakit_separate_voice_adapter.py` | New adapter contract tests |
| `docs/api-keys.md`, `docs/tools.md`, `docs/api-reference.md`, `docs/security.md`, `docs/architecture.md`, `README.md` | Replace OpenAPI audio-separation references with MediaKit |
| `.agents/skills/modelark-mcp/SKILL.md` | Rewrite audio-separation section |
| `specs/SPEC_VOD_OPENAPI_PROVIDER_CONTRACT.md` | Mark `status: deprecated`, point to MediaKit |
| `specs/SPEC_VOD_MEDIAKIT_PROVIDER_CONTRACT.md` | Add separate-voice request/task contract |
| `plans/PLAN_BYTEPLUS_VOD_AUDIO_SEPARATION.md` | Mark `status: superseded` |

## Validation

- `uv run ruff check src tests && uv run ruff format --check src tests`
- `uv run mypy src`
- `uv run pytest tests/contract/test_vod_mediakit_separate_voice_adapter.py tests/integration/test_vod_audio_separation_tool.py tests/integration/test_mcp_conformance.py -q`
- `uv run pytest -q` (full suite)
