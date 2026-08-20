# API Reference

Complete schemas, inputs, outputs, and examples for the conditional MCP tool
surface.

## Tool Inventory

| # | Tool | Product | Type | Auth |
|---|---|---|---|---|
| 1 | `seed_audio_generate` | Seed Audio | Synchronous | Seed Speech |
| 2 | `seed_audio_generate_variations` | Seed Audio | Parallel | Seed Speech |
| 3 | `seedream_generate_image` | Seedream | Synchronous | ModelArk |
| 4 | `seedream_generate_image_variations` | Seedream | Parallel | ModelArk |
| 5 | `seedance_create_task` | Seedance | Async task | ModelArk |
| 6 | `seedance_create_task_variations` | Seedance | Parallel async | ModelArk |
| 7 | `seedance_get_task` | Seedance | Poll | ModelArk |
| 8 | `seedance_list_tasks` | Seedance | Read-only | ModelArk |
| 9 | `seedance_cancel_or_delete_task` | Seedance | Destructive | ModelArk |
| 10 | `media_upload` | Object storage (optional) | Synchronous | TOS / S3 |
| 11 | `media_presign` | Object storage (optional) | Read-only | TOS / S3 |
| 12 | `vod_enhance_video` | VOD AI MediaKit (optional) | Async submission | MediaKit Bearer |
| 13 | `vod_transcode_video` | VOD AI MediaKit (optional) | Async task | MediaKit Bearer |
| 14 | `vod_get_transcode_task` | VOD AI MediaKit (optional) | Poll | MediaKit Bearer |
| 15 | `vod_separate_audio` | VOD AI MediaKit (optional) | Async submission | MediaKit Bearer |
| 16 | `vod_get_audio_separation` | VOD AI MediaKit (optional) | Poll | MediaKit Bearer |

## Tool Annotations

| Tool | readOnly | destructive | idempotent | openWorld |
|---|---|---|---|---|
| `seed_audio_generate` | false | false | false | true |
| `seed_audio_generate_variations` | false | false | false | true |
| `seedream_generate_image` | false | false | false | true |
| `seedream_generate_image_variations` | false | false | false | true |
| `seedance_create_task` | false | false | false | true |
| `seedance_create_task_variations` | false | false | false | true |
| `seedance_get_task` | true | false | true | false |
| `seedance_list_tasks` | true | false | true | false |
| `seedance_cancel_or_delete_task` | false | true | false | true |
| `media_upload` | false | false | false | true |
| `media_presign` | true | false | true | false |
| `vod_enhance_video` | false | false | false | true |
| `vod_transcode_video` | false | false | false | true |
| `vod_get_transcode_task` | true | false | true | false |
| `vod_separate_audio` | false | false | false | true |
| `vod_get_audio_separation` | true | false | true | false |

---

## vod_enhance_video

Enhance a public HTTPS video through the Bearer-authenticated BytePlus VOD AI
MediaKit convenience endpoint. The tool is registered only when
`BYTEPLUS_VOD_MEDIAKIT_API_KEY` is configured and requires the `vod:enhance`
scope in JWT mode.

The verified contract returns an accepted asynchronous task and deliberately fixes the
provider profile to `common` / `professional` / `4k` / `high` / 24 fps. It
does not expose polling. The POST is non-idempotent and is never retried
automatically because a timeout may occur after the provider began processing.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `video_url` | URL | Yes | — | Public HTTPS source; private, loopback, and link-local targets rejected |
| `scene` | `"common"` | No | `"common"` | Exact initial profile |
| `tool_version` | `"professional"` | No | `"professional"` | Exact initial profile |
| `resolution` | `"4k"` | No | `"4k"` | Exact initial profile |
| `bitrate_level` | `"high"` | No | `"high"` | Exact initial profile |
| `fps` | `24` | No | `24` | Frames per second |
| `project` | string | No | `"default"` | 1–128 characters; serialized upstream as `Project` |
| `input_duration_seconds` | number \| null | No | `null` | Positive; reserved for future pricing support |
| `persist` | boolean | No | `true` | Best-effort durable artifact copy |

### Output

Returns `VodEnhanceVideoOutput` with provider `byteplus-vod-mediakit` and
`status="accepted"` plus task/request IDs. If the provider directly returns a
completed result, status is `succeeded` and `source_url` is preserved whether
persistence succeeds, is skipped, or fails.

When `persist=true`, the server attempts an SSRF-safe copy into the artifact
store. Video persistence is capped at 200 MiB. `persistence` is one of
`not_applicable`, `persisted`, `failed`, or `not_requested`; `persistence_issue` safely explains
a failure without exposing the URL or credential. `video` contains the durable
`ArtifactRef` only when persistence succeeds. `estimated_cost_usd` is always
`null` until the convenience endpoint's pricing and billing-unit mapping are
confirmed.

The asynchronous acceptance shape is verified by a sanitized live probe. The
completed-output shape remains provisional; unknown shapes fail closed.

### Example

```json
{
  "video_url": "https://media.example.com/source.mp4",
  "scene": "common",
  "tool_version": "professional",
  "resolution": "4k",
  "bitrate_level": "high",
  "fps": 24,
  "project": "default",
  "persist": true
}
```

---

## vod_transcode_video

Submit an asynchronous BytePlus VOD AI MediaKit video transcoding task through
the Bearer-authenticated convenience endpoint. Registered only when
`BYTEPLUS_VOD_MEDIAKIT_API_KEY` is configured; requires the `vod:transcode`
scope in JWT mode.

The request body and `video` object field names and enums are verified from the
official AI MediaKit API reference. The default options reproduce the verified
portrait-to-720x720 letterbox profile. Submission returns `status="accepted"`
with a `task_id` for polling via `vod_get_transcode_task`. The non-idempotent
POST is never retried automatically because a timeout may occur after the
provider began processing.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `video_url` | URL | Yes | — | Public HTTPS source; private, loopback, and link-local targets rejected |
| `container_format` | `"MP4"` \| `"FLV"` \| `"MPEGTS"` | No | `"MP4"` | Output container format |
| `video` | VodTranscodeVideoOptions | No | default profile | See below |

**VodTranscodeVideoOptions:**

| Field | Type | Default | Constraints |
|---|---|---|---|
| `codec` | `"h264"` \| `"h265"` | `"h264"` | Output video codec |
| `scale_type` | `0` \| `1` \| `2` | `2` | `0` follow source, `1` long/short-side limit, `2` width/height limit |
| `scale_mode` | `0` \| `1` \| `2` | `2` | `0` no upsampling, `1` stretch, `2` letterbox with black bars |
| `scale_width` | integer \| null | `null` | px [0,4320]; only when `scale_type=2`; defaults to 720 |
| `scale_height` | integer \| null | `null` | px [0,4320]; only when `scale_type=2`; defaults to 720 |
| `scale_short` | integer \| null | `null` | px [0,4320]; only when `scale_type=1` |
| `scale_long` | integer \| null | `null` | px [0,4320]; only when `scale_type=1` |
| `bitrate_mode` | `"crf"` \| `"abr"` \| `"cbr"` | `"crf"` | Bitrate control mode |
| `bitrate_crf` | integer | `25` | [0,51]; only used when `bitrate_mode=crf` |
| `bitrate_kbps` | integer | `2000` | kbps [10,50000] |
| `fps_mode` | `"vfr"` \| `"cfr"` | `"vfr"` | Only takes effect after `fps` is set |
| `fps` | integer \| null | `null` | [1,240]; unset keeps source rate |
| `is_hdr_to_sdr` | boolean | `true` | Convert HDR to SDR; false keeps HDR |

### Output

Returns `VodTranscodeVideoOutput` with `provider` `byteplus-vod-mediakit`,
`status="accepted"`, task/request IDs, and a server-side heuristic
`recommended_poll_after_ms`.

### Example

```json
{
  "video_url": "https://media.example.com/portrait.mp4",
  "container_format": "MP4",
  "video": {
    "scale_type": 2,
    "scale_width": 720,
    "scale_height": 720,
    "scale_mode": 2
  }
}
```

---

## vod_get_transcode_task

Poll the status and output of a BytePlus VOD AI MediaKit transcode task.
Registered only when `BYTEPLUS_VOD_MEDIAKIT_API_KEY` is configured; requires the
`vod:read` scope in JWT mode.

### Input

| Field | Type | Required | Default |
|---|---|---|---|
| `task_id` | string | Yes | — |
| `persist_output` | boolean | No | `true` |

### Output

Returns `VodTranscodeTaskOutput` with `provider` `byteplus-vod-mediakit` and a
normalized `status` of `processing`, `succeeded`, or `failed` (the provider
documents only `running`/`completed`/`failed`). On success: `source_url`
(24-hour lifetime), optional `duration_seconds`/`resolution`/`video_codec`, and
normalized `created_at`/`finished_at`/`source_expires_at`. When
`persist_output=true` the completed output is copied once into the durable
artifact store (200 MiB cap) and cached by task ID; a persistence failure never
erases provider success. On failure, `error` carries the safe provider detail.

### Task Statuses

| Status | Meaning |
|---|---|
| `processing` | Provider reported `running`; still transcoding |
| `succeeded` | Provider reported `completed`; `source_url` available |
| `failed` | Provider reported `failed`; `error` populated |

### Example

```json
// Input
{ "task_id": "amk-tool-transcode-video-112738623234" }

// Output (succeeded)
{
  "provider": "byteplus-vod-mediakit",
  "task_id": "amk-tool-transcode-video-112738623234",
  "status": "succeeded",
  "provider_status": "completed",
  "duration_seconds": 15.07,
  "resolution": "720p",
  "video_codec": "h264",
  "source_url": "https://example.com/transcoded_video.mp4",
  "persistence": "persisted",
  "video": {
    "id": "71e9c2a8-...",
    "uri": "seed-media://artifacts/71e9c2a8-...",
    "media_type": "video",
    "mime_type": "video/mp4",
    "bytes": 1748096
  }
}
```

---

## vod_separate_audio

Submit an asynchronous BytePlus VOD AI MediaKit voice and background audio
separation task via `POST /api/v1/tools/separate-voice`. The tool is registered
when `BYTEPLUS_VOD_MEDIAKIT_API_KEY` is configured and requires the
`vod:extract` scope in JWT mode.

Input takes a public HTTPS source URL and separation options:

| Field | Type | Required | Description |
|---|---|---|---|
| `audio_url` | string | No | Public HTTPS audio URL (mp3, m4a, wav). Exactly one of `audio_url`/`video_url` |
| `video_url` | string | No | Public HTTPS video URL (mp4, flv, ts, avi, mov, wmv, mkv). Exactly one of `audio_url`/`video_url` |
| `scene` | string | No | `Audio` (default), `Music`, `Drama`, `Narrate` |
| `output_format` | string | No | `aac` (default), `mp3`, `wav`, `m4a`, `flac` |

Returns `VodSeparateAudioOutput` with `provider` `byteplus-vod-mediakit`,
`status` `accepted`, the provider `request_id` and `provider_log_id`, and the
`task_id` to pass to `vod_get_audio_separation`. The mutation is never retried
automatically because completion is ambiguous after a timeout.

### Example

```json
// Input
{ "video_url": "https://example.com/clip.mp4", "scene": "Drama" }

// Output
{
  "provider": "byteplus-vod-mediakit",
  "status": "accepted",
  "request_id": "20260820...",
  "provider_log_id": "20260820...",
  "task_id": "amk-tool-separate-voice-...",
  "recommended_poll_after_ms": 3000
}
```

---

## vod_get_audio_separation

Poll a BytePlus VOD AI MediaKit separate-voice task via `GET
/api/v1/tasks/{task_id}`. Registered when `BYTEPLUS_VOD_MEDIAKIT_API_KEY` is
configured and requires the `vod:read` scope in JWT mode.

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | Yes | Task ID returned by `vod_separate_audio` |
| `persist_output` | boolean | No | Copy completed tracks into durable artifact storage on first successful poll (default `true`) |

Returns `VodAudioSeparationTaskOutput` with a normalized `status` of
`processing`, `succeeded`, or `failed`. On success, `voice`, `background`,
`music`, and `sfx` each carry the track's expiring `source_url` (valid 24
hours) and, when best-effort persistence succeeds, a durable `artifact`
reference.

### Task Statuses

| Status | Meaning |
|---|---|
| `processing` | Provider reported `running`; still separating |
| `succeeded` | Provider reported `completed`; at least one track populated |
| `failed` | Provider reported `failed`; `error` populated |

### Example

```json
// Input
{ "task_id": "amk-tool-separate-voice-..." }

// Output (succeeded, 2-way)
{
  "provider": "byteplus-vod-mediakit",
  "task_id": "amk-tool-separate-voice-...",
  "status": "succeeded",
  "provider_status": "completed",
  "duration_seconds": 120.5,
  "voice": {
    "artifact": { "id": "...", "uri": "seed-media://artifacts/...", "media_type": "audio", "mime_type": "audio/aac", "bytes": 1787924 },
    "source_url": "https://vod.ap-southeast-1.byteplusvod.com/voice.aac?sign=...",
    "persistence": "persisted"
  },
  "background": {
    "artifact": { "id": "...", "uri": "seed-media://artifacts/...", "media_type": "audio", "mime_type": "audio/aac", "bytes": 1787924 },
    "source_url": "https://vod.ap-southeast-1.byteplusvod.com/background.aac?sign=...",
    "persistence": "persisted"
  }
}
```

---

## Shared Types

### MediaSource

A media reference by URL or Base64.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"url"` \| `"base64"` | Yes | Source type |
| `url` | string | If kind=url | HTTPS URL |
| `data` | string | If kind=base64 | Base64-encoded data |
| `mime_type` | string | No | MIME type |

### AudioReference

An audio reference for voice cloning.

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"speaker"` \| `"url"` \| `"base64"` | Yes | Reference mode |
| `speaker_id` | string | If kind=speaker | Preset speaker ID |
| `url` | string | If kind=url | Reference audio URL |
| `data` | string | If kind=base64 | Base64 audio data (WAV preflight-checked against 30s limit) |
| `mime_type` | string | No | MIME type |

### ArtifactRef

A durable reference to persisted media.

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique artifact ID |
| `uri` | string | `seed-media://artifacts/{id}` |
| `media_type` | `"image"` \| `"audio"` \| `"video"` | Logical type |
| `mime_type` | string | e.g. `image/png`, `audio/wav`, `video/mp4` |
| `bytes` | integer | Size in bytes |
| `sha256` | string | SHA-256 hex digest |
| `created_at` | string | ISO-8601 timestamp |
| `expires_at` | string | Local artifact expiry |
| `source_expires_at` | string | Provider URL expiry (2h audio, 24h image/video) |

### VariationResult

Result of a single variation within a parallel generation.

| Field | Type | Description |
|---|---|---|
| `index` | integer | 0-based variation index |
| `seed` | integer \| null | Seed used (image only) |
| `artifact` | ArtifactRef \| null | Generated artifact (null if failed) |
| `task_id` | string \| null | Task ID (Seedance only) |
| `error` | object \| null | Error details if failed |
| `request_id` | string \| null | Provider request ID |
| `provider_log_id` | string \| null | Provider log ID (Seed Audio) |

### VariationSummary

Aggregate result of a parallel generation.

| Field | Type | Description |
|---|---|---|
| `total` | integer | Total variations requested |
| `succeeded` | integer | Variations that produced output |
| `failed` | integer | Variations that failed |
| `variations` | list[VariationResult] | Per-variation results |

---

## 1. seed_audio_generate

Generate full-scene audio through Seed Speech.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `text_prompt` | string | Yes | — | 1-3000 chars |
| `audio_references` | list[AudioReference] | No | `[]` | Max 3 |
| `image_reference` | MediaSource | No | — | Mutually exclusive with audio |
| `output` | AudioOutputOptions | No | — | Format, rate, pitch |
| `watermark` | AudioWatermarkOptions | No | — | AIGC watermark |
| `persist` | boolean | No | `true` | Persist to artifact store |

### AudioOutputOptions

| Field | Type | Default | Constraints |
|---|---|---|---|
| `format` | `"wav"` \| `"mp3"` \| `"pcm"` \| `"ogg"` | — | — |
| `sample_rate` | integer | — | 8000-48000 |
| `speech_rate` | integer | — | -50 to 100 |
| `loudness_rate` | integer | — | -50 to 100 |
| `pitch_rate` | integer | — | -12 to 12 |
| `subtitle` | boolean | — | — |
| `subtitle_type` | `"utterance"` \| `"word"` | — | — |

### Output

| Field | Type | Description |
|---|---|---|
| `provider` | `"byteplus-seed-speech"` | Fixed |
| `model` | `"seed-audio-1.0"` | Fixed |
| `duration_seconds` | float | Output duration |
| `billing_duration_seconds` | float | Billed duration |
| `artifact` | ArtifactRef | Persisted audio |
| `subtitle` | Subtitle \| null | Optional subtitles |
| `request_id` | string | Request ID |
| `provider_log_id` | string \| null | X-Tt-Logid |

### Example

```json
// Input
{
  "text_prompt": "Welcome to BytePlus.",
  "output": { "format": "wav", "sample_rate": 44100 }
}

// Output
{
  "provider": "byteplus-seed-speech",
  "model": "seed-audio-1.0",
  "duration_seconds": 2.5,
  "billing_duration_seconds": 2.5,
  "artifact": {
    "id": "5828e515-...",
    "uri": "seed-media://artifacts/5828e515-...",
    "media_type": "audio",
    "mime_type": "audio/wav",
    "bytes": 2656078
  },
  "request_id": "",
  "provider_log_id": "20260721..."
}
```

---

## 2. seed_audio_generate_variations

Generate N independent audio variations in parallel.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `text_prompt` | string | No* | — | 1-3000 chars |
| `variations` | integer | No | 1 | 1-5 |
| `variation_prompts` | list[string] | No | — | Must have `variations` entries |
| `audio_references` | list[AudioReference] | No | `[]` | Max 3 |
| `image_reference` | MediaSource | No | — | Mutually exclusive with audio |
| `output` | AudioOutputOptions | No | — | — |
| `watermark` | AudioWatermarkOptions | No | — | — |
| `persist` | boolean | No | `true` | — |

\* Either `text_prompt` or `variation_prompts` must be provided.

### Output

| Field | Type | Description |
|---|---|---|
| `provider` | `"byteplus-seed-speech"` | Fixed |
| `model` | `"seed-audio-1.0"` | Fixed |
| `summary` | VariationSummary | Aggregate results |

### Example

```json
// Input
{
  "text_prompt": "Hello world",
  "variations": 3,
  "persist": true
}

// Output
{
  "provider": "byteplus-seed-speech",
  "model": "seed-audio-1.0",
  "summary": {
    "total": 3,
    "succeeded": 3,
    "failed": 0,
    "variations": [
      { "index": 0, "artifact": { "id": "...", "media_type": "audio", ... } },
      { "index": 1, "artifact": { "id": "...", "media_type": "audio", ... } },
      { "index": 2, "artifact": { "id": "...", "media_type": "audio", ... } }
    ]
  }
}
```

---

## 3. seedream_generate_image

Generate or edit an image through ModelArk Seedream.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `prompt` | string | Yes | — | — |
| `images` | list[MediaSource] | No | — | Reference images for editing |
| `model` | string | No | Configured model | Must be in capability registry |
| `size` | string | No | — | e.g. "1024x1024" |
| `seed` | integer | No | — | -1 = random, 0+ = fixed |
| `max_images` | integer | No | — | 1-15 (batch-capable models only) |
| `output_format` | `"png"` \| `"jpeg"` | No | — | Model-dependent |
| `response_format` | `"url"` \| `"b64_json"` | No | — | — |
| `watermark` | boolean | No | — | AIGC watermark |
| `prompt_optimization` | `"standard"` \| `"fast"` | No | — | — |
| `persist` | boolean | No | `true` | — |

### Output

| Field | Type | Description |
|---|---|---|
| `provider` | `"byteplus-modelark"` | Fixed |
| `model` | string | Model used |
| `created_at` | string | ISO-8601 |
| `artifacts` | list[ArtifactRef] | Persisted images |
| `item_errors` | list[SeedreamItemError] | Per-item failures |
| `usage` | SeedreamUsage | Token usage |

### Example

```json
// Input
{
  "prompt": "A serene mountain landscape at sunset",
  "size": "1024x1024",
  "seed": 42,
  "output_format": "jpeg"
}

// Output
{
  "provider": "byteplus-modelark",
  "model": "dola-seedream-5-0-pro-260628",
  "created_at": "2026-07-21T05:36:04+00:00",
  "artifacts": [
    {
      "id": "83ef8c61-...",
      "uri": "seed-media://artifacts/83ef8c61-...",
      "media_type": "image",
      "mime_type": "image/jpeg",
      "bytes": 428968
    }
  ],
  "item_errors": [],
  "usage": { "total_tokens": 4096 }
}
```

---

## 4. seedream_generate_image_variations

Generate N independent image variations in parallel with distinct seeds.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `prompt` | string | No* | — | — |
| `variations` | integer | No | 1 | 1-10 |
| `variation_prompts` | list[string] | No | — | Must have `variations` entries |
| `base_seed` | integer | No | — | -1 to 2147483647 |
| `images` | list[MediaSource] | No | — | Reference images |
| `model` | string | No | Configured | — |
| `size` | string | No | — | — |
| `output_format` | `"png"` \| `"jpeg"` | No | — | — |
| `response_format` | `"url"` \| `"b64_json"` | No | — | — |
| `watermark` | boolean | No | — | — |
| `prompt_optimization` | `"standard"` \| `"fast"` | No | — | — |
| `persist` | boolean | No | `true` | — |

\* Either `prompt` or `variation_prompts` must be provided.

### Seed Behavior

| `base_seed` | Per-variation seeds |
|---|---|
| `null` | Provider randomizes (not recorded) |
| `-1` | Client picks random (recorded) |
| `N` | `[N, N+1, N+2, ...]` (deterministic, modulo 2^31) |

### Output

| Field | Type | Description |
|---|---|---|
| `provider` | `"byteplus-modelark"` | Fixed |
| `model` | string | Model used |
| `created_at` | string | ISO-8601 |
| `summary` | VariationSummary | Aggregate results |

### Example

```json
// Input
{
  "prompt": "A futuristic city skyline, cyberpunk",
  "variations": 3,
  "base_seed": 42,
  "size": "1024x1024"
}

// Output
{
  "provider": "byteplus-modelark",
  "model": "dola-seedream-5-0-pro-260628",
  "created_at": "2026-07-21T...",
  "summary": {
    "total": 3,
    "succeeded": 3,
    "failed": 0,
    "variations": [
      { "index": 0, "seed": 42, "artifact": { "id": "16cfa323-...", ... } },
      { "index": 1, "seed": 43, "artifact": { "id": "86f189f2-...", ... } },
      { "index": 2, "seed": 44, "artifact": { "id": "6f5978c9-...", ... } }
    ]
  }
}
```

---

## 5. seedance_create_task

Create an asynchronous Seedance video generation task.

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `prompt` | string | No | — | 1-32,000 chars |
| `images` | list[SeedanceImageInput] | No | — | Max 9 |
| `videos` | list[SeedanceVideoInput] | No | — | Max 3 |
| `audios` | list[SeedanceAudioInput] | No | — | Max 3 |
| `model` | string | No | Configured | — |
| `resolution` | `"480p"` \| `"720p"` \| `"1080p"` \| `"4k"` | No | — | Model-dependent |
| `ratio` | string | No | — | e.g. "16:9". For `extend_video`, stripped (auto-locks to source) to prevent `InvalidParameter.TaskTypeConstraint`. For `edit_video`, auto-derived from input video. For first/last-frame, locks to first image. |
| `duration` | integer | No | — | -1 (auto) or 4-15. Ignored for edit tasks (auto-derived from input video) |
| `omni_reference_task_type` | string | No | `auto` | Task type hint (e.g. `edit_video`, `extend_video`) |
| `generate_audio` | boolean | No | — | — |
| `watermark` | boolean | No | — | — |
| `return_last_frame` | boolean | No | — | — |
| `execution_expires_after` | integer | No | — | 3600-259200 seconds |
| `priority` | integer | No | — | 0-9 |
| `safety_identifier` | string | No | — | Max 64 chars |

Text-only input (prompt with no media) is supported for pure text-to-video
generation. Audio cannot be the sole media input — at least a prompt,
image, or video is required.

#### Auto-locked parameters by task type

When the provider detects (or is hinted via `omni_reference_task_type`)
that the task is video editing, extension, or first/last-frame generation,
certain parameters are auto-derived from the input media and cannot be
overridden:

| Task type | Aspect ratio | Duration |
|---|---|---|
| Video editing | Locked to input video's ratio | Locked to input video's duration (±0.3s) |
| Video extension | Locked to input video's ratio | Set freely |
| First/last-frame generation | Locked to first image's ratio | Set freely |
| Text-to-video / standard reference | Set freely | Set freely (or `-1` for auto) |

### SeedanceImageInput

Extends `MediaSource` with a `role` field:

| Field | Type | Description |
|---|---|---|
| `role` | `"first_frame"` \| `"last_frame"` \| `"reference_image"` | Image purpose |

### SeedanceVideoInput

Video references are URL-only. Unlike image and audio references, there is no
Base64 path — videos must be uploaded to a publicly reachable HTTPS endpoint
before the tool is called. Use the `media_upload` tool to upload Base64 or
a local file (stdio only) to object storage (TOS or S3) and receive a presigned
HTTPS GET URL. Alternatively, host the video on your own HTTPS endpoint.
The URL must resolve to a public IP (loopback, private, and link-local
addresses are rejected by the SSRF policy).

| Field | Type | Description |
|---|---|---|
| `kind` | `"url"` | Always `url` (hard-coded) |
| `url` | string | Public HTTPS URL of the reference video |
| `role` | `"reference_video"` | Always `reference_video` |

### Output

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Task ID for polling |
| `status` | `"queued"` | Initial status |
| `recommended_poll_after_ms` | integer | Suggested poll delay |

### Example

```json
// Input
{
  "prompt": "A cat walking through a garden",
  "images": [
    { "kind": "url", "url": "https://...", "role": "reference_image" }
  ],
  "resolution": "480p",
  "duration": 5
}

// Output
{
  "task_id": "cgt-20260721134956-h5cz9",
  "status": "queued",
  "recommended_poll_after_ms": 5000
}
```

---

## 6. seedance_create_task_variations

Create N independent Seedance video tasks in parallel.

### Input

Inherits all fields from `seedance_create_task`, plus:

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `prompt` | string | No* | — | 1-32,000 chars |
| `variations` | integer | No | 1 | 1-5 |
| `variation_prompts` | list[string] | No | — | Must have `variations` entries; each 1-32,000 chars |

\* Either `prompt` or `variation_prompts` must be provided.

### Output

| Field | Type | Description |
|---|---|---|
| `summary` | VariationSummary | Per-variation task IDs |
| `recommended_poll_after_ms` | integer | Poll delay for all tasks |

### Example

```json
// Input
{
  "variation_prompts": [
    "The cat walks forward slowly",
    "The cat jumps playfully"
  ],
  "variations": 2,
  "images": [
    { "kind": "base64", "data": "...", "mime_type": "image/png", "role": "reference_image" }
  ],
  "resolution": "480p",
  "duration": 5
}

// Output
{
  "summary": {
    "total": 2,
    "succeeded": 2,
    "failed": 0,
    "variations": [
      { "index": 0, "task_id": "cgt-...-rq5gm" },
      { "index": 1, "task_id": "cgt-...-hj27l" }
    ]
  },
  "recommended_poll_after_ms": 5000
}
```

---

## 7. seedance_get_task

Retrieve the status and output of a Seedance task.

### Input

| Field | Type | Required | Default |
|---|---|---|---|
| `task_id` | string | Yes | — |
| `persist_output` | boolean | No | `true` |

### Output

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Task ID |
| `model` | string | Model used |
| `status` | SeedanceTaskStatus | Current status |
| `created_at` | string | ISO-8601 |
| `updated_at` | string | ISO-8601 |
| `error` | object \| null | Error details |
| `video` | ArtifactRef \| null | Persisted video (on success) |
| `last_frame` | ArtifactRef \| null | Persisted last frame |
| `usage` | SeedanceTaskUsage \| null | Token usage |
| `settings` | object | Generation settings |

### Task Statuses

| Status | Meaning |
|---|---|
| `queued` | Waiting to start |
| `running` | Generating |
| `succeeded` | Completed, video available |
| `failed` | Failed, check `error` |
| `expired` | Expired before completion |
| `cancelled` | Was cancelled |

### Example

```json
// Input
{ "task_id": "cgt-20260721134956-h5cz9" }

// Output (succeeded)
{
  "task_id": "cgt-...",
  "model": "dreamina-seedance-2-0-260128",
  "status": "succeeded",
  "created_at": "2026-07-21T06:02:19+00:00",
  "updated_at": "2026-07-21T06:06:13+00:00",
  "video": {
    "id": "71e9c2a8-...",
    "uri": "seed-media://artifacts/71e9c2a8-...",
    "media_type": "video",
    "mime_type": "video/mp4",
    "bytes": 1748096
  },
  "usage": { "completion_tokens": 48400 }
}
```

---

## 8. seedance_list_tasks

List recent Seedance tasks (last 7 days).

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `page` | integer | No | 1 | 1-500 |
| `page_size` | integer | No | 20 | 1-100 |
| `status` | SeedanceTaskStatus | No | — | Filter by status |
| `task_ids` | list[string] | No | — | Filter by IDs |
| `model` | string | No | — | Filter by model |
| `service_tier` | `"default"` \| `"flex"` | No | — | — |

### Output

| Field | Type | Description |
|---|---|---|
| `tasks` | list[SeedanceTaskSummary] | Task summaries |
| `total` | integer | Total matching tasks |
| `page` | integer | Current page |
| `page_size` | integer | Page size |
| `has_more` | boolean | More pages available |

---

## 9. seedance_cancel_or_delete_task

Cancel (queued) or delete (terminal) a Seedance task.

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | Yes | Task ID |
| `mode` | `"cancel"` \| `"delete"` | Yes | Operation |
| `expected_status` | `"queued"` \| `"succeeded"` \| `"failed"` \| `"expired"` | Yes | Expected current status |
| `confirm` | `true` | Yes | Explicit confirmation |

### DELETE Semantics

| Status | Cancel | Delete |
|---|---|---|
| `queued` | Yes | No |
| `running` | No | No |
| `succeeded` | No | Yes |
| `failed` | No | Yes |
| `expired` | No | Yes |
| `cancelled` | No | No |

### Output

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Task ID |
| `mode` | `"cancel"` \| `"delete"` | Operation performed |
| `previous_status` | string | Status before operation |
| `message` | string | Result message |

---

## Resources

### seed-media://artifacts/{artifact_id}

Returns persisted media by artifact ID with the correct MIME type.

```json
{
  "contents": [
    {
      "content": "<base64-encoded-bytes>",
      "mime_type": "image/png"
    }
  ],
  "meta": {
    "artifact_id": "83ef8c61-...",
    "media_type": "image"
  }
}
```

### seed-health://status

Returns server health and configuration status as plain text.

## 10. media_upload

Upload media to object storage (TOS or S3) and return a presigned HTTPS GET
URL. Registered when the selected object-storage backend credentials are set
(`TOS_*` with default `OBJECT_STORAGE_BACKEND=tos`, or `S3_*` with
`OBJECT_STORAGE_BACKEND=s3`).

### Input

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `media_type` | `"image"` \| `"audio"` \| `"video"` | yes | — | Media category |
| `mime_type` | string | yes | — | Must be in the allowed MIME list for the category |
| `data` | string | one of | — | Base64-encoded bytes. Mutually exclusive with `file_path` |
| `file_path` | string | one of | — | Local file path (stdio only). Mutually exclusive with `data` |
| `key_prefix` | string | no | `"references"` | Alphanumeric, `-`, `_`, `/` only |
| `expires_in_seconds` | integer | no | configured TTL | Presigned URL validity, 60–604800. Use a long value (e.g. 3600) for VOD inputs that are fetched asynchronously |

### Output

| Field | Type | Description |
|---|---|---|
| `url` | string | Presigned HTTPS GET URL |
| `expires_at` | string | ISO-8601 expiry timestamp |
| `object_key` | string | Object key |
| `bytes` | integer | Uploaded byte count |

### Example

```json
// Input
{
  "media_type": "video",
  "mime_type": "video/mp4",
  "data": "AAAAIGZ0cBAAA..."
}

// Output
{
  "url": "https://test-bucket.tos-ap-southeast-1.bytepluses.com/references/video/abc?X-Tos-Signature=...",
  "expires_at": "2026-07-24T07:30:00+00:00",
  "object_key": "references/video/abc",
  "bytes": 1048576
}
```

---

## 11. media_presign

Generate a fresh presigned HTTPS GET URL for an existing object in storage
(TOS or S3) without re-uploading. Use this when a previously uploaded
reference's presigned URL has expired or is about to expire. The object must
already exist in the bucket (uploaded via `media_upload`). No data is
transferred — only a new URL is minted.

### Input

| Field | Type | Required | Constraints |
|---|---|---|---|
| `object_key` | string | yes | Object key from a prior `media_upload` call. Alphanumeric, `-`, `_`, `/`; first char must be alphanumeric |
| `expires_in_seconds` | integer | no | Presigned URL validity, 60–604800. Use a long value (e.g. 3600) for VOD inputs that are fetched asynchronously |

### Output

| Field | Type | Description |
|---|---|---|
| `url` | string | Fresh presigned HTTPS GET URL |
| `expires_at` | string | ISO-8601 expiry timestamp |
| `object_key` | string | Object key the URL grants access to |

### Example

```json
// Input
{
  "object_key": "references/video/abc-123-def"
}

// Output
{
  "url": "https://test-bucket.tos-ap-southeast-1.bytepluses.com/references/video/abc-123-def?X-Tos-Signature=...",
  "expires_at": "2026-07-24T07:30:00+00:00",
  "object_key": "references/video/abc-123-def"
}
```

---

## Operational HTTP endpoints

When Streamable HTTP is enabled, the ASGI application also exposes:

| Path | Purpose |
|---|---|
| `/health` | Process liveness |
| `/ready` | Runtime, SQLite state, and artifact-directory readiness |
| `/metrics` | Prometheus metrics exposition |

These are operational endpoints rather than MCP resources. Protect their
network reachability at the ingress or reverse-proxy layer.
