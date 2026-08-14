---
title: BytePlus VOD AI MediaKit Provider Contract
status: proposed
horizon: current
created: 2026-08-12
updated: 2026-08-14
tags:
  - byteplus-vod
  - ai-mediakit
  - provider-contract
source:
  - https://docs.byteplus.com/en/docs/byteplus-vod/docs-image-enhancement-template
  - https://docs.byteplus.com/en/docs/byteplus-vod/reference-startexecution
  - https://docs.byteplus.com/en/docs/byteplus-vod/reference-getexecution
  - https://docs.byteplus.com/zh-CN/docs/byteplus-vod/ai-mediakit-create-a-video-transcoding-task
  - https://docs.byteplus.com/en/docs/byteplus-vod/ai-mediakit-get-task-details
related:
  - plans/PLAN_BYTEPLUS_VOD_AI_MEDIAKIT_VIDEO_ENHANCEMENT.md
  - plans/PLAN_BYTEPLUS_VOD_AI_MEDIAKIT_VIDEO_TRANSCODING.md
---

<!-- markdownlint-disable MD013 MD025 -->

# BytePlus VOD AI MediaKit Provider Contract

## Scope and Verification Status

This specification governs the Bearer-authenticated convenience endpoints supplied
for MCP integration on the AI MediaKit data plane:

- `POST /api/v1/tools/enhance-video` (video enhancement, `vod_enhance_video`);
- `POST /api/v1/tools/transcode-video` + `GET /api/v1/tasks/{task_id}` (video
  transcoding, `vod_transcode_video` / `vod_get_transcode_task`).

It does not describe the separately documented, AK/SK-signed BytePlus VOD
`StartExecution` and `GetExecution` APIs. The two surfaces must not share adapters
or credentials.

### Video enhancement surface

Verification is **partial** as of 2026-08-12:

- the endpoint route, method, request body, Bearer authentication, unauthenticated
  error envelope, and `x-tt-logid` response header are directly verified;
- two approved credentialed probes directly verified that successful submission
  is asynchronous and returns top-level `task_id` and `request_id` fields;
- the polling/result endpoint, output URL lifetime/host chain, MIME, size metadata,
  retry guarantees, and idempotency are not publicly documented;
- the MCP implementation therefore exposes only the exact supplied request profile,
  does not add polling, does not retry ambiguous POST failures, and rejects unknown
  successful response shapes rather than guessing.

### Video transcoding surface

Verification is **complete for the request and task contracts** as of 2026-08-14
from the official AI MediaKit API reference (rendered via the zh-CN/zh-TW
variants, which carry identical English content, cross-confirmed on two
independent pages):

- the transcode request body (top-level and `video`/`audio` object field names and
  enum values) is documented and confirmed (see [Video Transcoding Request
  Contract](#video-transcoding-request-contract));
- the task polling endpoint `GET /api/v1/tasks/{task_id}` and its status/result/error
  shapes are documented and confirmed (see [Video Transcoding Task Contract](#video-transcoding-task-contract));
- the output URL lifetime (24 hours), idempotency (`client_token` plus a default
  24-hour deduplication key), and callback model are documented;
- the **output URL hostname and every redirect hop** were verified by a sanctioned
  live probe on 2026-08-14: the output host is
  `*.vod.ap-southeast-1.byteplusvod.com` (`.byteplusvod.com` suffix), which has
  been added to the artifact store's trusted-host policy. Durable persistence now
  works for confirmed outputs.
- `queue_id` and `Project` as *request* parameters are **unverified** and must not
  be exposed to clients.

## Authentication and Endpoint

```http
POST /api/v1/tools/enhance-video HTTP/2
Host: mediakit.ap-southeast-1.bytepluses.com
Authorization: Bearer ${BYTEPLUS_VOD_MEDIAKIT_API_KEY}
Content-Type: application/json
Accept: application/json
```

The credential is process configuration only. It must never be accepted as a tool
argument, logged, included in fixtures, or committed.

## Request Contract

The initial implementation accepts only the supplied profile:

```json
{
  "video_url": "https://media.example.com/source.mp4",
  "scene": "common",
  "tool_version": "professional",
  "resolution": "4k",
  "bitrate_level": "high",
  "fps": 24,
  "Project": "default"
}
```

| Field | MCP field | Type | Initial constraint |
| --- | --- | --- | --- |
| `video_url` | `video_url` | HTTPS URL | Public provider-fetchable video URL; no embedded credentials or local/private/link-local destination. |
| `scene` | `scene` | string | Literal `common`. |
| `tool_version` | `tool_version` | string | Literal `professional`. |
| `resolution` | `resolution` | string | Literal `4k`. |
| `bitrate_level` | `bitrate_level` | string | Literal `high`. |
| `fps` | `fps` | integer | Literal `24`. |
| `Project` | `project` | string | Non-empty, maximum 128 characters; serialized with case-sensitive alias `Project`. |

Broader values require official documentation or a sanitized credentialed contract
probe and a spec update.

## Verified Error Contract

An unauthenticated empty JSON request returns HTTP 401, JSON content type, and:

```json
{
  "success": false,
  "error": {
    "code": "AuthenticationError",
    "type": "Unauthorized",
    "message": "The API key in the request is missing or invalid. Set valid api-key to proceed."
  }
}
```

The response includes `x-tt-logid`, which is the preferred diagnostic request ID.
Error parsing accepts this verified envelope and safely falls back to the HTTP status
when a different error body is returned. Provider response bodies and source URLs
must not be logged.

## Verified Asynchronous Acceptance Contract

An approved credentialed probe returned HTTP 200, JSON content type,
`x-tt-logid`, and the following sanitized shape:

```json
{
  "success": true,
  "task_id": "amk-tool-enhance-video-sanitized",
  "request_id": "request-id-sanitized"
}
```

The adapter returns this as `status="accepted"`, stores the task under the
provider-scoped ownership key `vod-mediakit`, and sets persistence to
`not_applicable`. The body `request_id` and header `x-tt-logid` are preserved
separately as `request_id` and `provider_log_id`.

This acceptance shape is specific to the enhancement surface. No polling/result
route was found in official documentation for the enhancement Bearer surface. The
documented AK/SK-signed VOD direct-edit progress/result APIs are a different
contract and must not be assumed compatible. (The transcode surface *does* have a
documented polling route — see [Video Transcoding Task Contract](#video-transcoding-task-contract).)

## Provisional Completed-Result Compatibility Boundary

If BytePlus later returns a completed result directly, the adapter provisionally
supports a JSON success envelope with `success: true` and an object
under `data` or `result`. That object must contain one HTTPS output URL under
`output_url`, `video_url`, or `url`. These aliases are a narrow compatibility
boundary, not a claim that all are provider-documented.

The adapter may preserve these optional fields when present:

- `request_id` (body fallback when `x-tt-logid` is absent);
- `task_id` or `id`;
- `status`;
- `mime_type` or `content_type`;
- `expires_at` or `expiration` as an ISO-8601 string;
- `output_size_bytes` or `size` as a non-negative integer;
- terminal `error.code` and `error.message`.

Unknown or malformed HTTP 2xx bodies raise a normalized, non-retryable
`INVALID_RESPONSE` provider error. The implementation does not invent a polling
path from a returned ID. A later verified contract replaces this compatibility
boundary and updates fixtures before broadening behavior.

## Execution and Retry Semantics (video enhancement)

- Submission is verified asynchronous. No polling, result, cancellation, list,
  or callback endpoint is verified for enhancement; only
  `vod_enhance_video` is registered for that surface.
- POST timeout, connection loss after dispatch, and HTTP 5xx are treated as
  ambiguous completion. They are not retried automatically.
- HTTP 429 is retryable only as provider guidance for a new user-initiated attempt;
  the mutation is not automatically replayed.
- Other 4xx responses are non-retryable until corrected.

## Output and Persistence Contract (video enhancement)

- An accepted response returns its task ID with `persistence="not_applicable"`.
- A parsed completed response always returns its provider `source_url` to the
  authorized caller, even if local persistence is skipped or fails.
- The URL path/query is never logged. `source_expires_at` is returned only when the
  provider supplies it; the server does not invent a lifetime.
- Every initial output hostname and redirect hop must pass URL/IP validation and the
  repository's trusted-host policy. No output or redirect host has yet been verified
  beyond the API hostname.
- Durable video persistence is best-effort and capped at 209,715,200 bytes by the
  current artifact policy. A larger result remains a provider success with
  `persistence="failed"` and `output_too_large`.
- Persistence failure never changes provider `status="succeeded"` into a provider
  error. It returns a structured safe issue and preserves request/task/source-expiry
  metadata.

## Video Transcoding Request Contract

`POST /api/v1/tools/transcode-video` with Bearer auth and `Content-Type:
application/json`. Submission is asynchronous; a successful submission returns a
top-level `task_id` for polling.

### Top-level request fields

| Field | Type | Required | Allowed values / notes |
| --- | --- | --- | --- |
| `video_url` | String | Yes | Public HTTP/HTTPS URL. Source formats: mp4, flv, ts, avi, mov, wmv, mkv. |
| `container_format` | String | Yes | `MP4` (default), `FLV`, `MPEGTS`. |
| `video` | Object | Yes | See below. |
| `audio` | Object | No | Omitted → audio transcoded with `aac`, other params matching source. |
| `metadata_keep_tags` | Array[String] | No | e.g. `["title","artist"]`; no effect when `container_format=MPEGTS`. |
| `metadata_add_tags` | Array[Object] | No | `[{"key":"album","value":"2024 Remaster"}]`; no effect for MPEGTS. |
| `client_token` | String | No | Idempotency token; case-sensitive, ≤64 printable ASCII. |
| `callback_args` | String | No | Custom args ≤512 bytes, returned as-is in the completion event. |
| `callback_url` | String | No | Task-scoped callback endpoint; must be a public http(s) URL. |

### `video` object fields

| Field | Type | Default | Allowed values / constraints |
| --- | --- | --- | --- |
| `codec` | String | `h264` | `h264`, `h265`. |
| `scale_type` | Integer | `0` | `0` = follow-source (no scaling; scale fields ignored); `1` = long/short-side limit (activates `scale_short`/`scale_long`); `2` = width/height limit (activates `scale_width`/`scale_height`). |
| `scale_mode` | Integer | `0` | Effective when `scale_type` ∈ {1,2}: `0` = no upsampling (shrink only); `1` = stretch to target W×H; `2` = letterbox (scale to fit, black-bar padding). |
| `scale_width` | Integer | — | [0, 4320]; only when `scale_type=2`; if only width or height given, the other scales proportionally. |
| `scale_height` | Integer | — | [0, 4320]; only when `scale_type=2`. |
| `scale_short` | Integer | — | [0, 4320]; only when `scale_type=1`. |
| `scale_long` | Integer | — | [0, 4320]; only when `scale_type=1`. |
| `bitrate_mode` | String | `crf` | `crf` (Constant Rate Factor), `abr` (average bitrate), `cbr` (constant bitrate). |
| `bitrate_crf` | Number | `25` | [0, 51] (0 = lossless); only when `bitrate_mode=crf`. |
| `bitrate_kbps` | Integer | `2000` | [10, 50000]; crf = max limit / abr = average target / cbr = constant target. |
| `fps_mode` | String | `vfr` | `vfr` (fps = max limit, source kept if lower), `cfr` (forced constant); only takes effect after `fps` is set. |
| `fps` | Integer | — | [1, 240]; if unset, source frame rate is kept. |
| `is_hdr_to_sdr` | Boolean | `true` | `false` keeps HDR. |

### `audio` object fields (optional; not exposed in the initial MCP tool)

`codec` (only `aac`), `sample_rate` (default 44100; one of 8000/11025/12000/16000/
22050/24000/32000/44100/48000/64000/88200/96000), `bitrate_mode` (`cbr` default;
`cae` only when `audio.codec=aac`), `bitrate_kbps` ([10,500], default 128),
`channels` (1 mono / 2 stereo default), `volume_method` (`2Pass`),
`volume_integrated_loudness` (LUFS [-70,-5], default -12),
`volume_true_peak` (dBTP [-9,0], default 0), `volume_loudness_range` (LU [1,20], default 7).

### Submission response

Synchronous HTTP 200 acceptance:

```json
{
  "success": true,
  "task_id": "amk-tool-transcode-video-...",
  "request_id": "..."
}
```

On failure: `success=false`, `error: { "code": "InvalidParameter"|"MissingParameter"|"InternalServiceError", "type": "...", "message": "...", "param": "..." }`.

### Idempotency

`client_token` (≤64 printable ASCII, case-sensitive) forces a deduplication key.
Without it, the provider uses a default key of account + core request parameters
with a 24-hour window. A timed-out or ambiguous POST therefore *may* be safely
re-submitted with identical body/token to recover the original task, but the MCP
adapter still treats POST timeout/5xx as ambiguous and does not retry blindly.

## Video Transcoding Task Contract

`GET /api/v1/tasks/{task_id}` with Bearer auth polls a task.

### Documented status values

- `running` (also worded as "processing") — still executing;
- `completed` — success; the `result` object is populated;
- `failed` — terminal failure; the `error` object is populated.

`queued`, `expired`, and `cancelled` are **not documented** for AI MediaKit tasks
and must not be invented. The MCP adapter maps `running` → `processing`,
`completed` → `succeeded`, `failed` → `failed`; any other value fails closed as
`INVALID_RESPONSE`.

### Completed response

```json
{
  "success": true,
  "task_id": "amk-tool-transcode-video-112738623234",
  "task_type": "transcode-video",
  "status": "completed",
  "result": {
    "duration": 15.07,
    "resolution": "720p",
    "video_codec": "h264",
    "video_url": "https://example.com/transcoded_video.mp4?auth_key=..."
  },
  "expires_at": 1780472196,
  "created_at": 1780385775,
  "finished_at": 1780385797,
  "request_id": "...",
  "queue_id": "default"
}
```

- `result.video_url` is valid for **24 hours** by default.
- `expires_at` / `created_at` / `finished_at` are Unix-seconds timestamps (docs
  describe them as strings, examples show integers — the adapter accepts both and
  normalizes to ISO-8601 UTC for MCP output). The server does not invent a lifetime.
- `result.resolution` ∈ {`240p`, `360p`, `480p`, `540p`, `720p`, `1080p`, `2k`, `4k`, ...}.

### Failed-task error object

```json
{
  "code": "DownloadFailed",
  "message": "Failed to download file ...",
  "param": "video_url",
  "type": "TaskError"
}
```

`type` is `TaskError` for execution errors or `ApiError` for API errors. Error
messages are sanitized (URLs redacted) before being returned to clients.

### Transcode execution and retry semantics

- POST timeout / connection loss after dispatch / HTTP 5xx → ambiguous completion,
  never retried blindly (idempotency makes re-submission safe for the user, but the
  adapter does not auto-replay).
- GET polling errors: 429 is retryable (via `Retry-After`); other 4xx non-retryable;
  5xx on GET is treated as ambiguous by the gateway (consistent with POST) and is
  not retried automatically within `call_with_retry` — the client must re-poll.
- No cancellation or list endpoint is documented; no such tool is exposed.

### Transcode persistence contract

Same durable-persistence rules as enhancement: best-effort, capped at 209,715,200
bytes, per-redirect-hop validation, `source_url` always returned to the authorized
caller, persistence failures never erase provider success, and `source_url`
path/query never logged. The output hostname (`*.byteplusvod.com`) was confirmed
by a live probe on 2026-08-14 and added to the artifact store's trusted-host
policy; durable persistence works for confirmed outputs.

## Regional and Billing Boundaries

The endpoint hostname identifies `ap-southeast-1`, but this alone does not prove that
the convenience surface has the same availability or billing model as the current
VOD enhancement product. Official VOD documentation states that upgraded enhancement
is available in Johor and legacy enhancement remains in Singapore. Public VOD prices
must not be applied to this convenience endpoint unless BytePlus confirms the mapping;
the MCP returns no cost estimate while that mapping is unverified.

## Required Follow-Up Evidence

Before declaring this contract accepted or production-ready, obtain provider
documentation or sanitized evidence for:

- the Bearer-surface polling/result endpoint and lifecycle states (transcode:
  confirmed; enhancement: still missing);
- output URL hostname plus every redirect hostname (transcode: confirmed
  `*.byteplusvod.com` on 2026-08-14; enhancement: still missing);
- URL lifetime, MIME, size metadata, and maximum output size (transcode lifetime:
  24h confirmed);
- validation, quota, 429, and 5xx error envelopes;
- idempotency/reconciliation guarantees and pricing mapping (transcode idempotency:
  `client_token` + 24h default key confirmed);
- `queue_id` and `Project` as request parameters (unverified — the projects-and-queues
  guide is currently unreachable);
- whether the convenience surface supports cancellation, list, or event callbacks
  (callbacks are documented; cancellation/list are not).
