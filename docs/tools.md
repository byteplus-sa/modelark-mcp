# Tools Reference

The server exposes a conditional set of typed tools. `seed_media_get_artifact`
is always available, provider tools are registered only when their credentials
are configured, and `media_upload` is registered only when TOS credentials are
present. Each tool accepts a Pydantic input model and returns a Pydantic output
model as structured content. All tools accept a `ctx: Context` parameter for
progress reporting and logging.

## seed_media_get_artifact

Retrieve persisted media inline by artifact ID.

**Annotations:** `readOnlyHint=True`, `destructiveHint=False`,
`idempotentHint=True`, `openWorldHint=False`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `artifact_id` | string | Yes | Artifact ID returned by a previous generation call |

### Output

Returns `SeedMediaGetArtifactOutput` with `artifact_id`, `media_type`,
`mime_type`, `sha256`, `bytes`, and Base64 `data`.

## seed_audio_generate

Generate full-scene audio through Seed Speech.

**Annotations:** `readOnlyHint=False`, `destructiveHint=False`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `text_prompt` | string | Yes | Text to synthesize (1-3000 chars) |
| `audio_references` | list[AudioReference] | No | Up to 3 audio references (speaker/url/base64) |
| `image_reference` | MediaSource | No | Image reference (mutually exclusive with audio) |
| `output` | AudioOutputOptions | No | Format, sample rate, speech rate, pitch |
| `watermark` | AudioWatermarkOptions | No | AIGC watermark controls |
| `persist` | boolean | No | Whether to persist output (default: true) |

### Output

Returns a `SeedAudioGenerateOutput` with `duration_seconds`,
`billing_duration_seconds`, `artifact`, optional `subtitle`, `request_id`,
`provider_log_id`, and optional `source_url`.

### Example

```json
{
  "text_prompt": "Hello, welcome to BytePlus."
}
```

## seedream_generate_image

Generate or edit an image through ModelArk Seedream.

**Annotations:** `readOnlyHint=False`, `destructiveHint=False`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | Yes | Text prompt for image generation |
| `images` | list[MediaSource] | No | Reference images for editing |
| `model` | string | No | Override configured model ID |
| `size` | string | No | Image dimensions (e.g. "1024x1024") |
| `max_images` | integer | No | Batch count (1-15, batch-capable models only) |
| `output_format` | "png" \| "jpeg" | No | Output format |
| `response_format` | "url" \| "b64_json" | No | Response format |
| `watermark` | boolean | No | AIGC watermark |
| `prompt_optimization` | "standard" \| "fast" | No | Prompt optimization mode |
| `persist` | boolean | No | Whether to persist output (default: true) |

### Output

Returns a `SeedreamGenerateOutput` with model, created timestamp, artifact
list, per-item errors, and usage info.

## seedream_edit_image

Edit an image through ModelArk Seedream with point or bounding-box targeting.

**Annotations:** `readOnlyHint=False`, `destructiveHint=False`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | Yes | Natural-language edit instruction |
| `images` | list[MediaSource] | Yes | Reference images to edit |
| `point` | EditCoordinate | No* | Point coordinate in normalized `0..999` space |
| `bbox` | EditBbox | No* | Bounding box in normalized `0..999` space |
| `model` | string | No | Override configured model ID |
| `size` | string | No | Image dimensions |
| `output_format` | "png" \| "jpeg" | No | Output format |
| `response_format` | "url" \| "b64_json" | No | Response format |
| `watermark` | boolean | No | AIGC watermark |
| `prompt_optimization` | "standard" \| "fast" | No | Prompt optimization mode |
| `persist` | boolean | No | Whether to persist output (default: true) |

\* Provide either `point` or `bbox`.

### Output

Returns `SeedreamEditOutput` with artifact list and usage information.

## seedance_create_task

Create an asynchronous Seedance video generation task.

**Annotations:** `readOnlyHint=False`, `destructiveHint=False`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | No | Text prompt |
| `images` | list[SeedanceImageInput] | No | Image inputs with roles |
| `videos` | list[SeedanceVideoInput] | No | Reference videos (max 3) |
| `audios` | list[SeedanceAudioInput] | No | Reference audio (max 3) |
| `model` | string | No | Override configured model ID |
| `resolution` | "480p" \| "720p" \| "1080p" \| "4k" | No | Output resolution |
| `ratio` | string | No | Aspect ratio |
| `duration` | integer | No | Duration in seconds (-1 for auto, 4-15) |
| `generate_audio` | boolean | No | Generate audio for the video |
| `watermark` | boolean | No | AIGC watermark |
| `return_last_frame` | boolean | No | Return last frame as image |
| `execution_expires_after` | integer | No | Task TTL in seconds (3600-259200) |
| `priority` | integer | No | Priority (0-9) |
| `safety_identifier` | string | No | Safety identifier (max 64 chars) |

At least one image or video input is required. Audio cannot be the sole
media input.

### Output

Returns a `SeedanceCreateTaskOutput` with task ID, status, and recommended
poll delay in `recommended_poll_after_ms`.

## seedance_get_task

Retrieve the status and output of a Seedance task.

**Annotations:** `readOnlyHint=True`, `destructiveHint=False`,
`idempotentHint=True`, `openWorldHint=False`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | Yes | Task ID to retrieve |
| `persist_output` | boolean | No | Persist video/last-frame on success (default: true) |

### Output

Returns a `SeedanceTaskOutput` with status, error (if any), video/last-frame
artifact references (on success), usage, and generation settings.

## seedance_list_tasks

List recent Seedance video generation tasks (last 7 days).

**Annotations:** `readOnlyHint=True`, `destructiveHint=False`,
`idempotentHint=True`, `openWorldHint=False`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `page` | integer | No | Page number (1-500) |
| `page_size` | integer | No | Page size (1-100, server caps at 100) |
| `status` | SeedanceTaskStatus | No | Filter by status |
| `task_ids` | list[string] | No | Filter by task IDs |
| `model` | string | No | Filter by model |
| `service_tier` | "default" \| "flex" | No | Filter by service tier |

### Output

Returns a `SeedanceTaskPage` with task summaries, total count, and
pagination info.

## seedance_cancel_or_delete_task

Cancel (queued) or delete (terminal) a Seedance task.

**Annotations:** `readOnlyHint=False`, `destructiveHint=True`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | Yes | Task ID |
| `mode` | "cancel" \| "delete" | Yes | Operation mode |
| `expected_status` | "queued" \| "succeeded" \| "failed" \| "expired" | Yes | Expected current status |
| `confirm` | true | Yes | Explicit confirmation required |

The handler fetches the current task state and rejects the operation if the
actual status does not match `expected_status`. This prevents accidental
cancellation of a running task.

### DELETE Semantics

| Current Status | Cancel | Delete |
|---|---|---|
| `queued` | Yes → `cancelled` | No |
| `running` | No | No |
| `succeeded` | No | Yes |
| `failed` | No | Yes |
| `expired` | No | Yes |
| `cancelled` | No | No |


## Parallel Generation Tools

The server also provides three parallel generation tools that generate
multiple variations in a single call using `asyncio.gather`. Each variation
runs independently — partial failures are captured per variation.

### seedream_generate_image_variations

Generate N independent image variations in parallel with distinct seeds.

**Input:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | No* | — | Base prompt for all variations |
| `variations` | integer | No | 1 | Number of variations (1-10) |
| `variation_prompts` | list[string] | No | — | Explicit prompts per variation |
| `base_seed` | integer | No | — | Base seed. None=random. -1=client-random. N=deterministic (N+i) |
| `images` | list[MediaSource] | No | — | Reference images |
| `model` | string | No | — | Override configured model |
| `size` | string | No | — | Image dimensions |
| `output_format` | "png" \| "jpeg" | No | — | Output format |
| `response_format` | "url" \| "b64_json" | No | — | Response format |
| `watermark` | boolean | No | — | AIGC watermark |
| `prompt_optimization` | "standard" \| "fast" | No | — | Optimization mode |
| `persist` | boolean | No | true | Persist to artifact store |

\* Either `prompt` or `variation_prompts` must be provided.

**Output:** `VariationSummary` with `total`, `succeeded`, `failed`, and
per-variation results (artifact or error).

### seed_audio_generate_variations

Generate N independent audio variations in parallel.

**Input:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `text_prompt` | string | No* | — | Base prompt (1-3000 chars) |
| `variations` | integer | No | 1 | Number of variations (1-5) |
| `variation_prompts` | list[string] | No | — | Explicit prompts per variation |
| `audio_references` | list[AudioReference] | No | — | Up to 3 audio references |
| `image_reference` | MediaSource | No | — | Image reference (mutually exclusive with audio) |
| `output` | AudioOutputOptions | No | — | Format, sample rate, etc. |
| `watermark` | AudioWatermarkOptions | No | — | AIGC watermark |
| `persist` | boolean | No | true | Persist to artifact store |

\* Either `text_prompt` or `variation_prompts` must be provided.

### seedance_create_task_variations

Create N independent Seedance video tasks in parallel. Returns task IDs
for async polling via `seedance_get_task`.

**Input:** Inherits all fields from `seedance_create_task`, plus:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `variations` | integer | No | 1 | Number of variations (1-5) |
| `variation_prompts` | list[string] | No | — | Explicit prompts per variation |

\* Either `prompt` or `variation_prompts` must be provided.

**Output:** `VariationSummary` + `recommended_poll_after_ms`.

## media_upload

Upload image, audio, or video media to BytePlus TOS and receive a presigned
HTTPS URL.

**Annotations:** `readOnlyHint=False`, `destructiveHint=False`,
`idempotentHint=False`, `openWorldHint=True`

### Input

| Field | Type | Required | Description |
|---|---|---|---|
| `media_type` | "image" \| "audio" \| "video" | Yes | Media category for validation |
| `mime_type` | string | Yes | MIME type such as `video/mp4` or `image/png` |
| `data` | string | No* | Base64-encoded media bytes |
| `file_path` | string | No* | Absolute local path; intended for stdio transport |
| `key_prefix` | string | No | Optional object key prefix |

\* Provide exactly one of `data` or `file_path`.

### Output

Returns `MediaUploadOutput` with presigned `url`, `expires_at`, `object_key`,
and uploaded `bytes`.
