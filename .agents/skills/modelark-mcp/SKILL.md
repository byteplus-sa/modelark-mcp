---
name: modelark-mcp
description: Guide for using the ModelArk Seed Multimodal MCP server to generate or edit images, audio, and video, poll and manage Seedance tasks, upload reference media to TOS, and fetch persisted artifacts.
---

# ModelArk Seed Multimodal MCP Server

Use this skill when the user wants to work with the local `modelark-mcp`
server and its typed BytePlus multimodal tool surface.

The server is built on FastMCP v3 and wraps three provider families behind one
local MCP server:

- **Seedream** for image generation and editing.
- **Seed Audio** for full-scene audio generation.
- **Seedance** for asynchronous video generation.
- **Artifacts** for durable media access after provider URLs expire.
- **TOS upload** for URL-only media workflows such as Seedance video
  references.

## When To Use

Invoke this skill when the user wants to:

- generate or edit an image;
- generate audio, voice-clone from references, or request several variations;
- create, poll, list, cancel, or delete Seedance video tasks;
- fetch a previously persisted artifact by ID;
- upload local or Base64 media to TOS to obtain a presigned HTTPS URL;
- verify which products are configured on the running server.

## Registration Model

Do not assume a fixed tool count. Registration is conditional:

### Always registered

- `seed_media_get_artifact`
- `seed-health://status` resource

### Requires `BYTEPLUS_SEED_AUDIO_API_KEY`

- `seed_audio_generate`
- `seed_audio_generate_variations`

### Requires `BYTEPLUS_MODELARK_API_KEY`

- `seedream_generate_image`
- `seedream_edit_image`
- `seedream_generate_image_variations`
- `seedance_create_task`
- `seedance_create_task_variations`
- `seedance_get_task`
- `seedance_list_tasks`
- `seedance_cancel_or_delete_task`

### Requires `TOS_ACCESS_KEY`, `TOS_SECRET_KEY`, and `TOS_BUCKET`

- `media_upload`

## Quick Start

### Prerequisites

- Python 3.12+
- `uv`
- BytePlus credentials for the product surfaces you need

### Minimum environment

```bash
BYTEPLUS_MODELARK_API_KEY=your-modelark-key
BYTEPLUS_SEED_AUDIO_API_KEY=your-seed-audio-key
```

Optional TOS upload support:

```bash
TOS_ACCESS_KEY=your-ak
TOS_SECRET_KEY=your-sk
TOS_BUCKET=your-private-bucket
```

### Running

```bash
uv run modelark-mcp
MCP_TRANSPORT=http uv run modelark-mcp
```

Verify configuration with `seed-health://status`, `/health`, or `/ready`.

## Tool Guide

### Artifact access

#### `seed_media_get_artifact`

Use when the client needs inline artifact content instead of reading the
resource URI directly.

- Input: `artifact_id`
- Returns: `artifact_id`, `media_type`, `mime_type`, `sha256`, `bytes`,
  Base64 `data`
- Behavior: read-only, idempotent, ownership-checked

#### `seed-media://artifacts/{artifact_id}`

Use when the client can consume an MCP resource directly.

- Returns the persisted media bytes with the correct MIME type
- Best for durable access to generated media after provider URLs expire

### Seed Audio

#### `seed_audio_generate`

Generate full-scene audio from a text prompt.

- Supports: voice cloning via `audio_references`, image-guided audio via
  `image_reference`, subtitles, watermarking, durable persistence
- Constraint: `audio_references` and `image_reference` are mutually exclusive
- Returns: `artifact`, `duration_seconds`, `billing_duration_seconds`,
  optional `subtitle`, `request_id`, `provider_log_id`, optional `source_url`

#### `seed_audio_generate_variations`

Generate 1 to 5 audio variations in parallel.

- Use when the user wants multiple options from one prompt family
- Supports `variation_prompts` for fully customized per-variation prompts
- Returns a variation summary with per-variation success or error capture

### Seedream

#### `seedream_generate_image`

Generate or reference-edit images.

- Supports: prompt-only generation, reference-image generation, seeds for
  reproducibility, batch generation on batch-capable families, prompt
  optimization, persistence
- Use this for general text-to-image and non-spatial reference editing
- Returns: `artifacts` plus usage data

#### `seedream_edit_image`

Use for coordinate-based editing with explicit spatial targeting.

- Requires at least one input image
- Requires either `point` or `bbox`
- Coordinates are normalized to `0..999`
- Use this instead of `seedream_generate_image` when the instruction depends on
  an exact point or region
- Returns: `artifacts` plus usage data

#### `seedream_generate_image_variations`

Generate 1 to 10 image variations in parallel.

- Supports `base_seed` for deterministic seed sequences
- Supports `variation_prompts` when each variation should differ semantically
- Returns a variation summary with per-variation artifact or error details

### Seedance

Seedance is asynchronous. The standard pattern is create, wait, poll, then
optionally clean up.

Task lifecycle:

```text
queued -> running -> succeeded | failed | cancelled | expired
```

#### `seedance_create_task`

Create a video generation task.

- Supports prompt plus image, video, and audio references
- Important constraint: at least one image or video is required; audio cannot
  be the sole media input
- Supports `return_last_frame`, `generate_audio`, `priority`, and task TTL
- Returns: `task_id`, `status="queued"`, `recommended_poll_after_ms`

#### `seedance_create_task_variations`

Create 1 to 5 Seedance tasks in parallel.

- Use when the user wants multiple candidate videos
- Returns per-variation task IDs and recommended poll delays

#### `seedance_get_task`

Poll a Seedance task and retrieve outputs.

- Input: `task_id`, optional `persist_output=true`
- On first successful retrieval, persists the returned video and optional last
  frame into the artifact store
- Returns: `task_id`, `model`, timestamps, `status`, optional `error`,
  optional `video`, optional `last_frame`, optional `usage`, `settings`
- Respect `recommended_poll_after_ms` from creation responses

#### `seedance_list_tasks`

List recent tasks from the last 7 days.

- Supports filtering by `status`, `task_ids`, `model`, and `service_tier`
- Use this for operational review, not output retrieval

#### `seedance_cancel_or_delete_task`

Destructive task cleanup.

- `mode="cancel"` only applies to `expected_status="queued"`
- `mode="delete"` applies to terminal tasks such as `succeeded`, `failed`, or
  `expired`
- Requires `confirm=true`

### TOS upload helper

#### `media_upload`

Upload media to BytePlus TOS and receive a presigned HTTPS URL.

- Supports `media_type` of `image`, `audio`, or `video`
- Accepts either Base64 `data` or absolute `file_path`
- `file_path` is intended for local `stdio` use
- Especially useful for URL-only workflows such as Seedance video references
- Returns: `url`, `expires_at`, `object_key`, `bytes`

## Recommended Workflows

### Durable generation

1. Call a generate tool with `persist=true` unless the user explicitly wants an
   ephemeral provider URL.
2. Save the returned `ArtifactRef.uri`.
3. Use the artifact URI or `seed_media_get_artifact` for later retrieval.

### Seedance polling

1. Call `seedance_create_task`.
2. Wait at least `recommended_poll_after_ms`.
3. Poll with `seedance_get_task` until the task reaches a terminal state.
4. Use the returned `video` and `last_frame` artifact refs when present.

### URL-only video references

1. If the user has Base64 video or a local video file, call `media_upload`.
2. Pass the returned presigned HTTPS URL into `seedance_create_task`.

### Choosing the right image tool

- Use `seedream_generate_image` for prompt-based generation or broad
  reference-based editing.
- Use `seedream_edit_image` for point or bounding-box edits.
- Use the `_variations` tool when the user asks for multiple options.

## Environment Essentials

### Provider credentials

- `BYTEPLUS_MODELARK_API_KEY` enables Seedream and Seedance
- `BYTEPLUS_SEED_AUDIO_API_KEY` enables Seed Audio

### Model selection

- `SEEDREAM_DEFAULT_MODEL`
- `SEEDANCE_DEFAULT_MODEL`
- `SEEDREAM_MODEL_FAMILY`
- `SEEDANCE_MODEL_FAMILY`
- `SEEDREAM_MODEL_BINDINGS`
- `SEEDANCE_MODEL_BINDINGS`

Use bindings when a custom model ID is not one of the built-in defaults.

### Transport and auth

- `MCP_TRANSPORT` or `FASTMCP_TRANSPORT`
- `MCP_HOST` or `FASTMCP_HOST`
- `MCP_PORT` or `FASTMCP_PORT`
- `MCP_AUTH_MODE`
- `MCP_JWT_JWKS_URI`
- `MCP_JWT_ISSUER`
- `MCP_JWT_AUDIENCE`
- `MCP_TENANT_CLAIM`

### Persistence and runtime

- `ARTIFACT_BACKEND`
- `ARTIFACT_DIR`
- `ARTIFACT_TTL_SECONDS`
- `MCP_INLINE_MEDIA_MAX_BYTES`
- `MCP_HTTP_MAX_BODY_BYTES`
- `PROVIDER_MAX_CONCURRENCY`
- `PRINCIPAL_MAX_CONCURRENCY`
- `DAILY_BUDGET_USD`
- `MODELARK_LOG_LEVEL`

### TOS upload

- `TOS_ACCESS_KEY`
- `TOS_SECRET_KEY`
- `TOS_SECURITY_TOKEN`
- `TOS_BUCKET`
- `TOS_REGION`
- `TOS_ENDPOINT`
- `TOS_PRESIGN_TTL_SECONDS`

## Guardrails And Pitfalls

- Generated provider URLs expire quickly. Persist outputs unless the user only
  needs immediate access.
- Tool availability depends on configuration. If a tool is missing, check
  `seed-health://status` and the relevant env vars before assuming a bug.
- Do not poll Seedance aggressively. Respect `recommended_poll_after_ms`.
- Use `seedream_edit_image` for spatial edits; do not force point or bbox logic
  into `seedream_generate_image`.
- Video references are URL-only. Use `media_upload` when the user starts with
  local or Base64 video input.
- Custom model IDs must be explicitly bound to a supported family.
- Budget enforcement is optional. `DAILY_BUDGET_USD=0` records usage without
  blocking.

## Server Notes

- ModelArk uses Bearer auth and powers Seedream plus Seedance.
- Seed Audio uses `X-Api-Key` and a separate Seed Speech endpoint.
- The server persists outputs locally and exposes them as durable MCP
  artifacts.
- HTTP mode also exposes `/health`, `/ready`, and `/metrics`.
