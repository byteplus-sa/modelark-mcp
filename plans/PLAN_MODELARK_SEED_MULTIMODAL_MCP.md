---
title: ModelArk Seed Multimodal MCP Server Plan
type: project
status: active
created: 2026-07-20
updated: 2026-07-20
tags:
  - byteplus
  - modelark
  - mcp
  - seedance
  - seedream
  - seed-audio
source:
  - https://docs.byteplus.com/en/docs/ModelArk/1298459
  - https://docs.byteplus.com/en/docs/ModelArk/1520757
  - https://docs.byteplus.com/en/docs/ModelArk/1541523
  - https://docs.byteplus.com/en/docs/byteplusvoice/seedaudio-01
  - https://modelcontextprotocol.io/specification/2025-11-25/server/tools
related:
  - "[[40 Technology/BytePlus Products/2026-07-14 - Seed Speech vs Seed Audio]]"
  - "[[50 Research/2026-07-13 - Seed Audio Cookbooks and Docs]]"
  - "[[40 Technology/BytePlus Products/2026-07-13 - BytePlus Seedance Advanced Creation Benefits]]"
---

<!-- markdownlint-disable MD013 MD025 MD060 -->

# ModelArk Seed Multimodal MCP Server Plan

> [!important] Scope assumption
> The request repeated “Seedance.” Existing vault context confirms that similar requests used “Seedance” when they meant the still-image model, Seedream. This plan therefore covers **Seed Audio**, **Seedance** video, and **Seedream** image. If the third product was something else, only that adapter and its tools need to change.

## Outcome

Build a TypeScript MCP server that exposes BytePlus multimodal generation through a small, typed, safe tool surface:

- Seed Audio full-scene audio generation through Seed Speech;
- Seedream image generation and editing through ModelArk;
- Seedance asynchronous video generation and task management through ModelArk;
- durable MCP resources for generated media whose provider URLs expire;
- local `stdio` first, with protected Streamable HTTP as a deployable option.

The most important research result is that this is **not one upstream API**. Seedance and Seedream share the ModelArk data-plane host and Bearer authentication, while Seed Audio is hosted by Seed Speech and uses `X-Api-Key`. The MCP server needs two provider gateways behind one normalized domain layer.

## Research Method

Three bounded sub-agent tracks researched Seed Audio, Seedance, and Seedream independently. The orchestrator then checked the official BytePlus documentation index, opened or fetched the cited live pages, verified current MCP SDK/specification behavior, and preserved contradictions instead of guessing.

All live sources were accessed on **2026-07-20**. Official BytePlus and Model Context Protocol sources take precedence over older vault notes and third-party wrappers.

## Verified API Inventory

| Product | Official surface | Authentication | Execution | Output lifetime |
|---|---|---|---|---|
| Seed Audio 1.0 | `POST https://voice.ap-southeast-1.bytepluses.com/api/v3/tts/create` | `X-Api-Key` | Non-streaming, single request/response | Returned URL is valid for 2 hours |
| Seedream | `POST {MODELARK_BASE_URL}/images/generations` | `Authorization: Bearer <API key>` | Synchronous JSON by default; supported models can stream partial images | Returned URL is valid for 24 hours |
| Seedance | `POST {MODELARK_BASE_URL}/contents/generations/tasks` plus task APIs | `Authorization: Bearer <API key>` | Provider-native asynchronous task | Video and last-frame URLs are valid for 24 hours; list history is 7 days |

ModelArk AP base URL: `https://ark.ap-southeast.bytepluses.com/api/v3`. The official image API also documents `https://ark.eu-west.bytepluses.com/api/v3`; API keys, model activation, and endpoint IDs are region-scoped. The implementation must make the base URL configurable and must not silently mix regions. See [ModelArk base URL and authentication](https://docs.byteplus.com/en/docs/ModelArk/1298459) and [Image generation API](https://docs.byteplus.com/en/docs/ModelArk/1541523).

### Seed Audio 1.0

Seed Audio is under **Seed Speech**, not the ModelArk data-plane API. The official [Audio 1.0 API reference](https://docs.byteplus.com/en/docs/byteplusvoice/seedaudio-01) documents:

- required `model: "seed-audio-1.0"` and `text_prompt` of at most 3,000 characters;
- optional `X-Api-Request-Id` UUID and diagnostic `X-Tt-Logid` response header;
- text-only generation when `references` is absent;
- up to three audio references, each using exactly one of `speaker`, `audio_data`, or `audio_url`;
- one image reference using exactly one of `image_data` or `image_url`;
- no mixing of audio and image references;
- audio references up to 30 seconds and 10 MB each in WAV, MP3, PCM, or OGG Opus;
- one reference image up to 10 MB in JPEG, PNG, or WebP;
- output formats WAV, MP3, PCM, or OGG Opus and a maximum output of 120 seconds;
- `speech_rate` from `-50` to `100`, `loudness_rate` from `-50` to `100`, and `pitch_rate` from `-12` to `12`;
- optional utterance- and word-level subtitle timestamps;
- explicit and metadata-based AIGC watermark controls;
- response fields `code`, `message`, Base64 `audio`, `duration`, billing `original_duration`, two-hour `url`, and optional `subtitle`.

> [!warning] Verified documentation contradiction
> The page lists the default WAV/PCM sample rate as `40000`, but the accepted-value list omits `40000` and includes `8000`, `16000`, `24000`, `32000`, `44100`, and `48000`. The MCP should omit `sample_rate` by default and only accept the explicit documented values until BytePlus confirms whether `40000` is valid.

Current official billing is published: pay-as-you-go is USD 0.15 per generated minute, billing uses `original_duration` with one-second precision, and activation includes a 60-minute trial. See [Audio 1.0 billing](https://docs.byteplus.com/en/docs/byteplusvoice/audiopricing). The current API, billing, and console pages no longer mention the invite-only/Lark-whitelist path recorded in older vault notes. Treat the older access and pricing notes as stale pending product-team confirmation.

### Seedream image generation and editing

The same [Image generation API](https://docs.byteplus.com/en/docs/ModelArk/1541523) performs text-to-image and editing. Adding `image` as a URL, data URI, or array of either selects reference-based generation/editing.

Current documented families include:

| Family | Example documented model ID | MCP capability stance |
|---|---|---|
| Seedream 5.0 Pro | `dola-seedream-5-0-pro-260628` | Single result, up to 10 references, precise editing, PNG/JPEG; no sequential generation or streaming |
| Seedream 5.0 Lite | `seedream-5-0-260128` / `seedream-5-0-lite-260128` | Up to 14 references, batch generation, streaming, PNG/JPEG |
| Seedream 4.5 | `seedream-4-5-251128` | Up to 14 references, batch/streaming, JPEG |
| Seedream 4.0 | `seedream-4-0-250828` | Up to 14 references, batch/streaming, JPEG |
| Seedream 3.0 T2I | `seedream-3-0-t2i-250415` | Deprecated/deactivated; do not expose as a default |

The official pages use inconsistent 5.0 Lite aliases. Model IDs must therefore be configuration, not hard-coded truth. The server will ship a capability registry keyed by logical family and let the operator bind the account-authorized model or endpoint ID.

Core request fields are `model`, `prompt`, optional `image`, `size`, `sequential_image_generation`, `sequential_image_generation_options.max_images`, `stream`, `output_format`, `response_format`, `watermark`, and `optimize_prompt_options.mode`. `response_format` is `url` or `b64_json`; URL outputs expire within 24 hours. Input images for current 4.x/5.x models can be up to 30 MB and 36 million pixels, and the current models support aspect ratios from 1:16 through 16:1.

MVP will force `stream: false`. Streaming events are useful but are incremental image delivery, not a durable job API. A later adapter can translate `image_generation.partial_succeeded`, `partial_failed`, `partial_image`, and `completed` events into MCP progress notifications.

### Seedance video task API

ModelArk exposes four operations:

| Operation | Method and path | MCP mapping |
|---|---|---|
| Create | `POST /contents/generations/tasks` | `seedance_create_task` |
| Retrieve | `GET /contents/generations/tasks/{id}` | `seedance_get_task` |
| List | `GET /contents/generations/tasks` | `seedance_list_tasks` |
| Cancel or delete | `DELETE /contents/generations/tasks/{id}` | `seedance_cancel_or_delete_task` |

The [create API](https://docs.byteplus.com/en/docs/ModelArk/1520757) accepts a `model` and a `content[]` array with `text`, `image_url`, `video_url`, and `audio_url` items. Important roles are `first_frame`, `last_frame`, `reference_image`, `reference_video`, and `reference_audio`.

For the Seedance 2.0 family, the current docs describe:

- 1-9 `reference_image` items;
- up to three reference videos, each 2-15 seconds, with total reference-video duration at most 15 seconds;
- MP4 or MOV reference video up to 200 MB each, 24-60 FPS;
- up to three reference audios in WAV or MP3, each 2-15 seconds and 15 MB, with total audio duration at most 15 seconds;
- reference audio cannot be the only media input; at least one image or video is required;
- controls including `resolution`, `ratio`, `duration` or `frames`, `seed`, `camera_fixed`, `watermark`, `generate_audio`, `return_last_frame`, `service_tier`, `execution_expires_after`, `priority`, and `safety_identifier`, subject to model support;
- current documented model IDs `dreamina-seedance-2-0-260128`, `dreamina-seedance-2-0-fast-260128`, and `dreamina-seedance-2-0-mini-260615`.

For Seedance 2.0 specifically, `duration` is `-1` or 4-15 seconds, `priority` is 0-9, `execution_expires_after` is 3,600-259,200 seconds, and `safety_identifier` is at most 64 English characters. The main 2.0 model supports 480p/720p/1080p/4K; Fast and Mini are limited to 480p/720p. Seedance 2.0 does **not** support `seed`, `camera_fixed`, `frames`, `draft`, or offline/flex `service_tier`, so the MVP schema will not expose those older-model controls.

The API also documents `callback_url`, but it does not document callback signing or verification. Do not expose callbacks in MVP; polling by task ID is safer until an authenticated callback contract is confirmed.

The [retrieve API](https://docs.byteplus.com/en/docs/ModelArk/1521309) returns `queued`, `running`, `cancelled`, `succeeded`, `failed`, or `expired`, plus provider error, timestamps, usage, generation settings, and successful `video_url`/optional `last_frame_url`. Output URLs expire in 24 hours.

The [list API](https://docs.byteplus.com/en/docs/ModelArk/1521675) queries only the previous seven days and supports page number/size plus status, task IDs, model, and service-tier filters. Page number and size are each documented from 1 to 500.

The [DELETE API](https://docs.byteplus.com/en/docs/ModelArk/1521720) has state-dependent semantics:

- `queued`: cancel and transition to `cancelled`;
- `running`: cannot cancel or delete;
- `succeeded`, `failed`, or `expired`: delete the task record;
- `cancelled`: cannot delete.

The MCP tool must not present this as a generic safe “cancel.” It will require an explicit `mode: "cancel" | "delete"`, fetch current state, and reject a mode/state mismatch before issuing DELETE.

## Architecture Decisions

1. **TypeScript on Node.js 24 LTS.** Node.js 24 is the current LTS line as of 2026-07-20; this choice also provides native `fetch`, `AbortSignal`, and modern test tooling. See the [official Node.js release table](https://nodejs.org/en/about/previous-releases).
2. **Use the stable MCP TypeScript SDK v1.x.** As of 2026-07-20 the official repository says v2 is pre-alpha and v1.x remains recommended for production. Install with `npm install @modelcontextprotocol/sdk zod`; do not copy v2 imports from `main`. See [MCP TypeScript SDK v1](https://ts.sdk.modelcontextprotocol.io/).
3. **Use direct HTTPS adapters, not one vendor SDK abstraction.** The two upstream hosts, authentication schemes, error shapes, and execution styles differ. A small `fetch`-based gateway keeps those differences explicit.
4. **Start with `stdio`; add stateless Streamable HTTP.** `stdio` minimizes local deployment risk. Streamable HTTP is the current remote transport, while legacy HTTP+SSE is deprecated. See [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
5. **Do not make experimental MCP Tasks an MVP dependency.** MCP Tasks are explicitly experimental in protocol revision `2025-11-25`, and client support varies. Seedance already exposes a durable provider task ID, so explicit create/get/list/cancel tools work everywhere. Add a task adapter only after the post-2026-07-28 specification and client ecosystem stabilize.
6. **Return structured content and artifact resources.** Each tool returns schema-validated `structuredContent` and a serialized text block for compatibility. Small images/audio may also be embedded as MCP image/audio content; video and large media use resource links. See [MCP tool result content](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
7. **Persist generated media immediately by default.** Provider URLs live for two hours or 24 hours. `ArtifactStore` copies outputs into local storage for `stdio` or an object store for remote deployments and returns `seed-media://artifacts/{id}`.
8. **Use a model capability registry.** Logical model families map to operator-configured model IDs and supported parameters. The server validates combinations before spending quota and can be updated without rewriting tool handlers.
9. **No arbitrary provider JSON pass-through.** Typed inputs prevent unsupported combinations, secret injection, and accidental exposure of newly added high-cost options.

## Component Design

```mermaid
flowchart LR
    Client["MCP client"] --> Transport["stdio or Streamable HTTP"]
    Transport --> Server["McpServer and tool registry"]
    Server --> Tools["Typed tool handlers"]
    Tools --> Policy["Input policy and capability validation"]
    Tools --> AudioService["Seed Audio service"]
    Tools --> ImageService["Seedream service"]
    Tools --> VideoService["Seedance task service"]
    AudioService --> SpeechGateway["Seed Speech gateway: X-Api-Key"]
    ImageService --> ModelArkGateway["ModelArk gateway: Bearer API key"]
    VideoService --> ModelArkGateway
    SpeechGateway --> BytePlusSpeech["voice.ap-southeast-1.bytepluses.com"]
    ModelArkGateway --> BytePlusArk["Configured ModelArk region"]
    AudioService --> ArtifactStore["ArtifactStore"]
    ImageService --> ArtifactStore
    VideoService --> ArtifactStore
    Server --> Resource["seed-media:// resource template"]
    Resource --> ArtifactStore
```

### Core interfaces

```ts
interface SeedAudioGateway {
  generate(input: SeedAudioProviderRequest, signal: AbortSignal): Promise<SeedAudioProviderResponse>;
}

interface SeedreamGateway {
  generate(input: SeedreamProviderRequest, signal: AbortSignal): Promise<SeedreamProviderResponse>;
}

interface SeedanceGateway {
  create(input: SeedanceCreateProviderRequest, signal: AbortSignal): Promise<{ id: string }>;
  get(id: string, signal: AbortSignal): Promise<SeedanceTask>;
  list(query: SeedanceListQuery, signal: AbortSignal): Promise<SeedanceTaskPage>;
  remove(id: string, signal: AbortSignal): Promise<void>;
}

interface ArtifactStore {
  putBase64(input: Base64ArtifactInput): Promise<ArtifactRef>;
  copyFromTrustedUrl(input: TrustedUrlArtifactInput): Promise<ArtifactRef>;
  get(id: string, auth: AuthContext): Promise<StoredArtifact>;
  deleteExpired(now: Date): Promise<number>;
}
```

Provider DTOs live only inside provider modules. Tool inputs and domain outputs are separate types so vendor field changes do not leak through the entire server.

## MCP Tool Contracts

### 1. `seed_audio_generate`

```ts
type MediaSource =
  | { kind: "url"; url: string }
  | { kind: "base64"; data: string; mimeType: string };

type AudioReference =
  | { kind: "speaker"; speakerId: string }
  | { kind: "url"; url: string }
  | { kind: "base64"; data: string; mimeType: string };

interface SeedAudioGenerateInput {
  textPrompt: string;                 // 1..3000 characters
  audioReferences?: AudioReference[]; // 0..3
  imageReference?: MediaSource;       // mutually exclusive with audioReferences
  output?: {
    format?: "wav" | "mp3" | "pcm" | "ogg_opus";
    sampleRate?: 8000 | 16000 | 24000 | 32000 | 44100 | 48000;
    speechRate?: number;              // -50..100
    loudnessRate?: number;            // -50..100
    pitchRate?: number;               // -12..12
    subtitles?: boolean;
  };
  watermark?: {
    audible?: boolean;
    metadata?: boolean;
    contentProducer?: string;
    produceId?: string;
    contentPropagator?: string;
    propagateId?: string;
  };
  persist?: boolean;                  // default true
}

interface SeedAudioGenerateOutput {
  provider: "byteplus-seed-speech";
  model: "seed-audio-1.0";
  durationSeconds: number;
  billingDurationSeconds: number;
  artifact: ArtifactRef;
  subtitle?: Subtitle;
  requestId: string;
  providerLogId?: string;
}
```

Validation uses a Zod `.superRefine()` to reject image+audio mixing, more than three references, invalid MIME types, and out-of-range controls. The adapter maps discriminated unions to the provider's `speaker`, `audio_url`, `audio_data`, `image_url`, or `image_data` fields.

### 2. `seedream_generate_image`

```ts
interface SeedreamGenerateInput {
  prompt: string;
  images?: MediaSource[];
  model?: string;                     // must be present in configured capability registry
  size?: string;                      // validated against selected model
  maxImages?: number;                 // 1..15; only batch-capable models
  outputFormat?: "png" | "jpeg";
  responseFormat?: "url" | "b64_json";
  watermark?: boolean;                // preserve provider default true unless explicitly set
  promptOptimization?: "standard" | "fast";
  persist?: boolean;                  // default true
}

interface SeedreamGenerateOutput {
  provider: "byteplus-modelark";
  model: string;
  createdAt: string;
  artifacts: ArtifactRef[];
  itemErrors: Array<{ index: number; code: string; message: string }>;
  usage: {
    generatedImages: number;
    inputImages?: number;
    outputTokens?: number;
    totalTokens?: number;
  };
}
```

The handler derives `sequential_image_generation` from `maxImages`, forces `stream: false` for MVP, and validates model-specific features. For example, Pro rejects batch/streaming fields, and 4.x rejects `outputFormat` until the API-reference/tutorial conflict is resolved.

### 3. `seedance_create_task`

```ts
type SeedanceImageInput = MediaSource & {
  role?: "first_frame" | "last_frame" | "reference_image";
};

type SeedanceVideoInput = Extract<MediaSource, { kind: "url" }> & {
  role: "reference_video";
};

type SeedanceAudioInput = MediaSource & {
  role: "reference_audio";
};

interface SeedanceCreateTaskInput {
  prompt?: string;
  images?: SeedanceImageInput[];
  videos?: SeedanceVideoInput[];
  audios?: SeedanceAudioInput[];
  model?: string;
  resolution?: "480p" | "720p" | "1080p" | "4k";
  ratio?: string;
  duration?: -1 | number;              // -1 or 4..15 for Seedance 2.0
  generateAudio?: boolean;
  watermark?: boolean;
  returnLastFrame?: boolean;
  executionExpiresAfter?: number;      // 3600..259200
  priority?: number;                   // 0..9
  safetyIdentifier?: string;           // <=64 English characters
}

interface SeedanceCreateTaskOutput {
  taskId: string;
  status: "queued";
  recommendedPollAfterMs: number;
}
```

The capability registry validates whether the selected model supports a field or resolution. Zod cross-field rules enforce Seedance 2.0 duration bounds, reference roles, media counts, and the rule that audio cannot be the sole media input. Draft/sample promotion and legacy Seedance 1.x prompt-suffix parameters are outside MVP.

### 4. `seedance_get_task`

```ts
interface SeedanceGetTaskInput {
  taskId: string;
  persistOutput?: boolean; // default true on success
}

type SeedanceTaskStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "succeeded"
  | "failed"
  | "expired";

interface SeedanceTaskOutput {
  taskId: string;
  model: string;
  status: SeedanceTaskStatus;
  createdAt: string;
  updatedAt: string;
  error?: NormalizedProviderError;
  video?: ArtifactRef;
  lastFrame?: ArtifactRef;
  usage?: { completionTokens?: number; totalTokens?: number };
  settings: Record<string, unknown>;
}
```

On first successful retrieval, copy 24-hour output URLs into `ArtifactStore`. Cache the mapping by provider task ID so repeated status checks do not download twice.

### 5. `seedance_list_tasks`

```ts
interface SeedanceListTasksInput {
  page?: number;       // 1..500
  pageSize?: number;   // 1..500, server default 20 and maximum policy 100
  status?: SeedanceTaskStatus;
  taskIds?: string[];
  model?: string;
  serviceTier?: "default" | "flex";
}
```

Return normalized task summaries and `total`. The server policy caps `pageSize` at 100 even though the provider accepts 500, avoiding oversized model context.

### 6. `seedance_cancel_or_delete_task`

```ts
interface SeedanceCancelOrDeleteInput {
  taskId: string;
  mode: "cancel" | "delete";
  expectedStatus: "queued" | "succeeded" | "failed" | "expired";
  confirm: true;
}
```

The handler first retrieves the task, compares current and expected status, enforces cancel-only-for-queued and delete-only-for-terminal states, then calls DELETE. Register it with `destructiveHint: true` and clear tool text describing the record-deletion behavior.

## MCP Resources and Results

Register a resource template:

```text
seed-media://artifacts/{artifactId}
```

`ArtifactRef` is the stable cross-tool contract:

```ts
interface ArtifactRef {
  id: string;
  uri: string;
  mediaType: "image" | "audio" | "video";
  mimeType: string;
  bytes?: number;
  sha256?: string;
  createdAt: string;
  expiresAt?: string;
  sourceExpiresAt?: string;
}
```

Every successful tool result returns:

1. `structuredContent` conforming to its output schema;
2. a concise serialized JSON text block for older MCP clients;
3. an MCP image or audio content block only when below `MCP_INLINE_MEDIA_MAX_BYTES`;
4. a `resource_link` for all persisted artifacts, especially video.

## Repository Structure

```text
modelark-seed-mcp/
├── package.json
├── package-lock.json
├── tsconfig.json
├── eslint.config.js
├── .env.example
├── src/
│   ├── index.ts
│   ├── config/
│   │   ├── env.ts
│   │   └── model-capabilities.ts
│   ├── server/
│   │   ├── build-server.ts
│   │   ├── stdio.ts
│   │   ├── http.ts
│   │   ├── results.ts
│   │   └── tools/
│   │       ├── seed-audio-generate.ts
│   │       ├── seedream-generate-image.ts
│   │       ├── seedance-create-task.ts
│   │       ├── seedance-get-task.ts
│   │       ├── seedance-list-tasks.ts
│   │       └── seedance-cancel-or-delete-task.ts
│   ├── domain/
│   │   ├── artifacts.ts
│   │   ├── errors.ts
│   │   ├── media.ts
│   │   └── models.ts
│   ├── providers/
│   │   ├── modelark/
│   │   │   ├── http-client.ts
│   │   │   ├── seedream.ts
│   │   │   ├── seedance.ts
│   │   │   └── schemas.ts
│   │   └── seed-speech/
│   │       ├── http-client.ts
│   │       ├── seed-audio.ts
│   │       └── schemas.ts
│   ├── artifacts/
│   │   ├── store.ts
│   │   ├── filesystem-store.ts
│   │   └── object-store.ts
│   ├── security/
│   │   ├── media-policy.ts
│   │   ├── url-policy.ts
│   │   └── auth-context.ts
│   └── observability/
│       └── logger.ts
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    ├── e2e/
    └── fixtures/
```

This keeps MCP protocol code, application behavior, provider DTOs, persistence, and security policy in separate layers with explicit interfaces.

## Configuration Contract

```dotenv
BYTEPLUS_MODELARK_API_KEY=
BYTEPLUS_MODELARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
BYTEPLUS_SEED_AUDIO_API_KEY=
BYTEPLUS_SEED_AUDIO_BASE_URL=https://voice.ap-southeast-1.bytepluses.com

SEEDREAM_DEFAULT_MODEL=dola-seedream-5-0-pro-260628
SEEDANCE_DEFAULT_MODEL=dreamina-seedance-2-0-260128

MCP_TRANSPORT=stdio
MCP_HOST=127.0.0.1
MCP_PORT=3000
MCP_ALLOWED_ORIGINS=

ARTIFACT_BACKEND=filesystem
ARTIFACT_DIR=.artifacts
ARTIFACT_TTL_SECONDS=604800
MCP_INLINE_MEDIA_MAX_BYTES=8388608

BYTEPLUS_CONNECT_TIMEOUT_MS=10000
BYTEPLUS_REQUEST_TIMEOUT_MS=300000
```

Provider credentials are startup configuration only and never tool arguments. If a credential is absent, do not register that product's tool set. Validate host URLs, model bindings, writable artifact storage, and incompatible configuration before accepting MCP requests.

## Security and Compliance

- **Secret handling:** redact `Authorization`, `X-Api-Key`, media Base64, signed URL query strings, and OAuth tokens. Never write provider keys to stdout, tool results, or fixtures.
- **`stdio` integrity:** only MCP JSON-RPC messages go to stdout; structured logs go to stderr, as required by the transport specification.
- **Remote authentication:** for Streamable HTTP, act as an OAuth resource server, publish Protected Resource Metadata, validate audience/issuer/scopes, and use HTTPS. Suggested scopes: `seed:audio:generate`, `seedream:generate`, `seedance:create`, `seedance:read`, and `seedance:delete`. See [MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).
- **Origin and host checks:** bind to `127.0.0.1` by default and validate the `Origin` header. Reject invalid origins with 403 to prevent DNS rebinding.
- **SSRF controls:** allow HTTPS input URLs only; reject loopback, link-local, private, multicast, and cloud metadata IPs after DNS resolution; cap redirects and revalidate every redirect target. Do not allow `file://` in remote mode.
- **Media limits:** preflight Base64 decoded size and MIME type before calling the provider. When the provider fetches a URL directly, still apply URL policy because the MCP can otherwise become an SSRF or exfiltration facilitator.
- **Artifact downloads:** only download returned URLs from configured BytePlus/TOS host allowlists. Strip query strings from logs and validate MIME/size before storage.
- **Human likeness and voice:** require the calling application to obtain consent. Do not bypass Seedance real-human checks or surface private asset-library APIs in MVP. Return the provider's actionable verification error and link the operator to the approved workflow.
- **Cost controls:** per-principal concurrency limits, maximum batch size, allowed-model list, request deadline, and optional daily budget counters. Never retry a billable generation blindly.

## Errors, Timeouts, and Retries

```ts
interface NormalizedProviderError {
  provider: "modelark" | "seed-speech";
  operation: string;
  httpStatus?: number;
  code?: string;
  message: string;
  requestId?: string;
  retryable: boolean;
  ambiguousCompletion?: boolean;
}
```

- Invalid MCP JSON or schema shape is a protocol error.
- Provider validation, moderation, access, quota, and execution failures are tool results with `isError: true`, structured content, and a concise correction path.
- Retry GET task retrieval/list on 429 and transient 5xx with jittered exponential backoff, respecting `Retry-After` when present.
- Do not automatically replay Seed Audio, Seedream, Seedance create, or DELETE calls. Provider idempotency is undocumented, and a network timeout may mean the billable operation succeeded.
- Set `ambiguousCompletion: true` when a mutation times out after request dispatch. Include the Seed Audio `X-Api-Request-Id` or Seedance task ID when known so an operator can reconcile.
- Wire MCP cancellation through `AbortSignal`. Cancelling the local request does not imply upstream Seedance task cancellation; that requires the explicit cancel tool.

## Observability

Emit structured stderr logs with:

- MCP tool name and correlation ID;
- upstream operation, HTTP status, provider request/log ID, and latency;
- Seedance task ID and status transition;
- artifact ID, MIME type, byte count, and persistence latency;
- rate-limit or retry decision;
- never prompt text, full media URLs, Base64, subtitles, or credentials by default.

For remote deployment, export counters and histograms for requests, errors by normalized code, generation latency, polling latency, artifact persistence failures, generated media count, and billed audio duration. Audit destructive task deletion with principal, task ID, prior status, and timestamp.

## Implementation Phases

### Phase 0 - Account and contract verification

1. Activate Seed Audio, Seedream, and Seedance in the intended BytePlus region/project.
2. Confirm the exact authorized Seedream and Seedance model or endpoint IDs in the console.
3. Run one minimal curl request for each product and save only redacted response fixtures.
4. Confirm whether the Seed Audio `40000` sample rate is accepted, whether `X-Api-Request-Id` is idempotent, and whether both `audio` and `url` are always returned.
5. Confirm required Seedance real-human/advanced-creation entitlement for the target use case.

Acceptance: three redacted golden fixtures, model bindings recorded in environment configuration, and unresolved contract questions explicitly documented.

### Phase 1 - Project scaffold and MCP skeleton

Create the project, then add dependencies through package-manager commands rather than editing dependency declarations by hand:

```bash
npm init -y
npm install @modelcontextprotocol/sdk zod
npm install -D typescript tsx vitest @types/node eslint typescript-eslint
```

Configure strict TypeScript, ESM, build/start/test/lint/typecheck scripts, environment validation, and an MCP `health` resource. Register placeholder tools with input/output schemas, then verify discovery with MCP Inspector over `stdio`.

Acceptance: build, typecheck, lint, and a tool-list smoke test pass without provider credentials leaking.

### Phase 2 - Provider gateways

Implement the two authenticated HTTP clients and three product adapters. Validate provider responses with Zod before mapping them to domain models. Capture ModelArk request IDs and Seed Speech `X-Tt-Logid`.

Use `undici`/native fetch and `MockAgent`-style contract tests or a minimal equivalent; do not add an HTTP abstraction library unless native fetch proves insufficient.

Acceptance: recorded fixtures cover success, 4xx validation/moderation, 401/403 access, 429 quota, 5xx, malformed JSON, timeout, and abort paths.

### Phase 3 - Tool schemas and services

Implement the six tool contracts and model capability registry. Add Zod cross-field rules, error normalization, tool annotations, structured results, and provider-task state mapping.

Acceptance: every invalid combination fails before network dispatch; every successful result matches its `outputSchema`; tool execution errors are actionable and contain no secrets.

### Phase 4 - Artifact persistence and resources

Implement filesystem storage first with atomic temp-file rename, SHA-256, MIME sniffing, ownership metadata, and TTL cleanup. Register `seed-media://artifacts/{id}` and return resource links. Add the object-store adapter only for remote deployment.

Acceptance: audio, image, video, and last-frame outputs survive provider URL expiry in a simulated test; unauthorized principals cannot read another tenant's artifact.

### Phase 5 - Transport and authorization hardening

Keep `stdio` as the default. Add stateless Streamable HTTP at `/mcp`, localhost binding, origin validation, request-size limits, OAuth resource-server middleware, scope checks, rate limiting, and per-principal job/artifact ownership.

Acceptance: MCP conformance/Inspector tests pass for both transports; invalid Origin, missing/invalid token, wrong audience, insufficient scope, and cross-tenant artifact/task lookups are rejected.

### Phase 6 - Live validation and release

Run opt-in live tests with the smallest billable settings and explicit cost approval. Validate one text-only audio, one reference image/audio mode, one Seedream generation/edit, and one Seedance create-to-success flow. Test queued cancellation if a reliable window is available; do not delete completed records merely to satisfy a test.

Publish a container image and server configuration example. Document client setup, model activation, expected URL retention, media-consent responsibilities, cost controls, and troubleshooting by normalized error code.

Acceptance: clean build/lint/typecheck/test run, live smoke report, dependency audit, no secrets in repository/history, and rollback instructions.

## Test Matrix

| Layer | Required coverage |
|---|---|
| Unit | Zod bounds/unions, model capability rules, task state machine, URL/IP policy, MIME/size checks, error mapping, redaction |
| Provider contract | Exact request headers/body/path and response parsing against official redacted fixtures |
| Integration | Tool handler to mock provider to artifact store; partial Seedream item failures; Seedance URL persistence |
| MCP protocol | Tool discovery, `inputSchema`, `outputSchema`, structured/text compatibility, resources, cancellation signal, annotations |
| Security | SSRF targets, redirect-to-private-IP, path traversal, oversized Base64, malicious MIME, origin spoofing, auth scope/tenant isolation |
| Live opt-in | One low-cost success per mode plus safe status retrieval; never run in default CI |

Live tests require `RUN_BYTEPLUS_LIVE_TESTS=1` and separate test credentials. CI must use mocks only.

## Sequence for Seedance

```mermaid
sequenceDiagram
    participant C as MCP client
    participant M as MCP server
    participant A as ModelArk
    participant S as Artifact store

    C->>M: seedance_create_task(input)
    M->>M: Validate model and media policy
    M->>A: POST /contents/generations/tasks
    A-->>M: task id
    M-->>C: taskId and poll guidance

    loop Until terminal
        C->>M: seedance_get_task(taskId)
        M->>A: GET /contents/generations/tasks/{id}
        A-->>M: queued, running, succeeded, failed, cancelled, or expired
        M-->>C: normalized task state
    end

    alt succeeded
        M->>S: Copy video and optional last frame
        S-->>M: durable artifact refs
        M-->>C: structured result and resource links
    else failed or expired
        M-->>C: normalized provider error
    end
```

## Risks and Open Questions

| Risk or unknown | Effect | Mitigation |
|---|---|---|
| The duplicated product name may not mean Seedream | Wrong third adapter | Confirm before implementation; adapter boundary isolates the change |
| Seedream 5.0 Lite aliases differ across official pages | 404/access failures | Operator-bound model/endpoint IDs and startup probe |
| Seedream API reference and tutorial conflict on 4.0 PNG | Invalid requests | Follow API reference and reject until confirmed |
| Seed Audio sample-rate default conflicts with allowed list | Validation or audio mismatch | Omit default; allow only listed values |
| Seed Audio has no published error taxonomy, QPS, timeout, or idempotency contract | Unsafe retries and weak diagnosis | No mutation replay; capture request/log IDs; confirm with product team |
| Provider output URLs expire in 2 or 24 hours | Broken MCP results | Persist immediately and return resource links |
| MCP Tasks and SDK v2 are not production-stable today | Client incompatibility | Stable SDK v1.x and explicit provider task tools; adapter later |
| Real-person or cloned-voice inputs require rights/consent | Legal and safety exposure | Human confirmation, approved asset workflow, audit logs, no bypass |
| Generated Base64 can exceed client/context limits | Transport failure or context bloat | Inline byte limit and artifact resources |
| Mutation timeout has ambiguous completion | Duplicate spend | No automatic retry; surface reconciliation identifiers |
| Region/model activation differs by account | Inconsistent behavior | Configurable base URL, regional keys, startup checks, live smoke test |

Questions to resolve before production:

1. What was the intended third product if not Seedream?
2. Which BytePlus region, project, model IDs, and endpoint IDs will production use?
3. Should generated artifacts live on local disk, BytePlus TOS, or an existing company object store?
4. Is this a personal/local `stdio` server or a multi-tenant remote service?
5. What are the allowed cost, concurrency, retention, and maximum media-size policies?
6. Does Seed Audio `X-Api-Request-Id` provide idempotency or diagnostics only?
7. Are Seed Audio access, region, error, and QPS details available through an internal product contract?
8. Should Seedream streaming and post-stable native MCP Tasks be scheduled for a second release?

## Source Conflicts and Confidence

Overall confidence is **high** for API hosts, authentication, methods, major request/response shapes, Seedance task states, and URL lifetimes because these were checked against current official pages.

Confidence is **medium** for exact default model identifiers across every BytePlus account and region. Treat model IDs as configuration.

Known conflicts preserved in this plan:

- Seed Audio `40000` default versus its documented allowed sample rates;
- Seedream 5.0 Lite alias/prefix inconsistency;
- Seedream 4.0 PNG example versus the API capability table;
- older vault claims of Seed Audio invite-only access/no public price versus current official activation and billing pages.

## Sources

### BytePlus

- [ModelArk base URL and authentication](https://docs.byteplus.com/en/docs/ModelArk/1298459) — official API authentication and regional base URL guidance, updated 2026-06-29.
- [Create a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1520757) — official Seedance request schema and media limits, updated 2026-06-29.
- [Retrieve a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1521309) — official task states and output fields, updated 2026-06-22.
- [List video generation tasks](https://docs.byteplus.com/en/docs/ModelArk/1521675) — official filters and seven-day history, updated 2026-06-22.
- [Cancel or delete a video generation task](https://docs.byteplus.com/en/docs/ModelArk/1521720) — official state-dependent DELETE behavior, updated 2026-06-22.
- [Image generation API](https://docs.byteplus.com/en/docs/ModelArk/1541523) — official Seedream schema, model capability notes, limits, and response, updated 2026-07-17.
- [Image streaming response](https://docs.byteplus.com/en/docs/ModelArk/1824137) — official Seedream streaming event schema, updated 2026-03-16.
- [ModelArk error codes](https://docs.byteplus.com/en/docs/ModelArk/1299023) — official validation, moderation, access, rate-limit, quota, and service errors, updated 2026-07-11.
- [ModelArk product updates](https://docs.byteplus.com/en/docs/ModelArk/1159177) — current Seedance/Seedream release signals, updated 2026-07-07.
- [Seed Audio 1.0 API reference](https://docs.byteplus.com/en/docs/byteplusvoice/seedaudio-01) — official audio request/response contract, updated 2026-07-09.
- [Seed Audio 1.0 billing](https://docs.byteplus.com/en/docs/byteplusvoice/audiopricing) — official pricing and billing unit, updated 2026-07-14.
- [Seed Speech console guide](https://docs.byteplus.com/en/docs/byteplusvoice/Speech_Console_Guide) — official activation and API-key flow, updated 2026-06-25.

### Runtime and Model Context Protocol

- [Node.js releases](https://nodejs.org/en/about/previous-releases) — official current/LTS status; Node.js 24 is LTS as of 2026-07-20.
- [MCP TypeScript SDK v1](https://ts.sdk.modelcontextprotocol.io/) — production SDK installation and capabilities.
- [MCP TypeScript server guide](https://ts.sdk.modelcontextprotocol.io/server) — `McpServer`, `stdio`, Streamable HTTP, stateless/stateful patterns, and DNS rebinding protection.
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) — schemas, structured content, image/audio content, resource links, error handling, and security requirements.
- [MCP transports specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) — `stdio`, Streamable HTTP, Origin validation, and localhost binding.
- [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) — OAuth resource-server behavior for remote HTTP.
- [MCP Tasks](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks) — experimental long-running task semantics and capability negotiation.

## Final Recommendation

Implement a **local-first, stable-SDK v1 MCP server with six typed tools and one artifact resource template**. Keep provider-native async behavior explicit for Seedance, keep Seed Audio and Seedream synchronous in MVP, persist all outputs, and defer Seedream streaming plus native MCP Tasks until real client support and the next MCP specification stabilize.

Before coding, complete Phase 0. The model-ID and Seed Audio contract checks are small but prevent the most expensive classes of rework: building against the wrong regional/model alias, retrying a billable request unsafely, or returning media links that expire before users can consume them.
