# Tools Reference

The server exposes six typed tools. Each accepts a Pydantic input model and
returns a Pydantic output model as structured content. All tools accept a
`ctx: Context` parameter for progress reporting and logging.

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

Returns a `SeedAudioGenerateOutput` with duration, billing duration, artifact
reference, optional subtitle, and provider log ID.

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
polling interval.

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
