# API Reference

Complete tool schemas, inputs, outputs, and examples for all nine MCP tools.

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
| `data` | string | If kind=base64 | Base64 audio data |
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
| `prompt` | string | No | — | — |
| `images` | list[SeedanceImageInput] | No | — | Max 9 |
| `videos` | list[SeedanceVideoInput] | No | — | Max 3 |
| `audios` | list[SeedanceAudioInput] | No | — | Max 3 |
| `model` | string | No | Configured | — |
| `resolution` | `"480p"` \| `"720p"` \| `"1080p"` \| `"4k"` | No | — | Model-dependent |
| `ratio` | string | No | — | e.g. "16:9" |
| `duration` | integer | No | — | -1 (auto) or 4-15 |
| `generate_audio` | boolean | No | — | — |
| `watermark` | boolean | No | — | — |
| `return_last_frame` | boolean | No | — | — |
| `execution_expires_after` | integer | No | — | 3600-259200 seconds |
| `priority` | integer | No | — | 0-9 |
| `safety_identifier` | string | No | — | Max 64 chars |

At least one image or video input is required. Audio cannot be the sole
media input.

### SeedanceImageInput

Extends `MediaSource` with a `role` field:

| Field | Type | Description |
|---|---|---|
| `role` | `"first_frame"` \| `"last_frame"` \| `"reference_image"` | Image purpose |

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
| `prompt` | string | No* | — | — |
| `variations` | integer | No | 1 | 1-5 |
| `variation_prompts` | list[string] | No | — | Must have `variations` entries |

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