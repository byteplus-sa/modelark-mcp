# Configuration

Configuration is loaded from environment variables or `.env` by Pydantic
Settings. Copy `.env.example` to `.env`. Empty values are ignored.

## Providers and models

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_MODELARK_API_KEY` | empty | Enables Seedream, Seedance, and Seed 2.1 understanding; sent as Bearer auth |
| `BYTEPLUS_SEED_AUDIO_API_KEY` | empty | Enables Seed Audio; sent as `X-Api-Key` |
| `BYTEPLUS_MODELARK_BASE_URL` | AP Southeast ModelArk URL | HTTPS data-plane base URL |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | AP Southeast Seed Speech URL | HTTPS service base URL |
| `SEEDREAM_DEFAULT_MODEL` | `dola-seedream-5-0-pro-260628` | Default image model/endpoint ID |
| `SEEDANCE_DEFAULT_MODEL` | `dreamina-seedance-2-0-260128` | Default video model/endpoint ID |
| `SEED_UNDERSTANDING_DEFAULT_MODEL` | `dola-seed-2-1-turbo-260628` | Default understanding model/endpoint ID |
| `SEEDREAM_MODEL_FAMILY` | empty | Family for a custom default: `pro`, `lite`, or `4x` |
| `SEEDANCE_MODEL_FAMILY` | empty | Family for a custom default: `standard`, `fast`, `mini`, or `seedance_2_5` |
| `SEED_UNDERSTANDING_MODEL_FAMILY` | empty | Family for a custom default: `pro` or `turbo` |
| `SEEDREAM_MODEL_BINDINGS` | empty | JSON list of `{model_id, family}` bindings |
| `SEEDANCE_MODEL_BINDINGS` | empty | JSON list of `{model_id, family}` bindings |
| `SEED_UNDERSTANDING_MODEL_BINDINGS` | empty | JSON list of `{model_id, family}` bindings |

The two built-in default IDs have known families. A custom ID must be bound
explicitly; the server does not infer capabilities from substrings in an ID.
For example:

```dotenv
SEEDREAM_DEFAULT_MODEL=my-image-endpoint
SEEDREAM_MODEL_BINDINGS=[{"model_id":"my-image-endpoint","family":"pro"}]
```

Credentials are startup-only. If a provider key is absent, its tools are not
registered.

## Transport and authentication

| Variable | Default | Purpose |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` or Streamable `http` |
| `MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `MCP_PORT` | `3000` | HTTP listen port |
| `MCP_ALLOWED_HOSTS` | loopback hosts | Comma-separated accepted Host headers |
| `MCP_ALLOWED_ORIGINS` | empty | Comma-separated accepted browser Origins |
| `MCP_HTTP_MAX_BODY_BYTES` | `10485760` | Maximum HTTP request body |
| `READINESS_CHECK_PROVIDERS` | `false` | When true, `/ready` also checks provider connectivity |
| `READINESS_PROVIDER_TIMEOUT_SECONDS` | `2.0` | Per-provider timeout for readiness checks |
| `RATE_LIMIT_RPM` | `0` | Max HTTP requests per minute per client IP; 0 disables |
| `RATE_LIMIT_BURST` | `0` | Token bucket burst size; 0 defaults to `RATE_LIMIT_RPM` |
| `MCP_AUTH_MODE` | `local` | `local` or `jwt` |
| `MCP_JWT_JWKS_URI` | empty | HTTPS JWKS endpoint for JWT verification |
| `MCP_JWT_ISSUER` | empty | Required token issuer |
| `MCP_JWT_AUDIENCE` | empty | Required token audience |
| `MCP_TENANT_CLAIM` | `tenant_id` | Claim used for tenant isolation |

`FASTMCP_TRANSPORT`, `FASTMCP_HOST`, and `FASTMCP_PORT` are accepted as
aliases for the corresponding `MCP_*` transport settings.

`local` auth is accepted only for stdio or loopback HTTP. Binding HTTP to a
non-loopback address fails closed unless JWT mode and all verifier settings are
present. JWT tokens must contain a principal (`sub`) and the configured tenant
claim. Tool scopes are enforced by FastMCP:

- `seed:audio:generate`
- `seedream:generate`
- `seedance:create`, `seedance:read`, `seedance:delete`
- `understanding:read`
- `media:upload`
- `media:presign`
- `artifacts:read`

## Seed Speech ASR (STT)

The `speech_to_text` tool is registered when `SEED_SPEECH_ASR_API_KEY` is
set — STT uses a dedicated ASR key, distinct from the TTS key. It submits
audio via HTTP, polls until transcription is complete, and returns the
complete `TranscriptionResult` in a single synchronous call. Audio input
accepts URL, Base64, or local file path (stdio only).

| Variable | Default | Purpose |
|---|---|---|
| `SEED_SPEECH_ASR_API_KEY` | empty | Enables speech-to-text; sent as `X-Api-Key` header |
| `SEED_SPEECH_ASR_BASE_URL` | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech ASR HTTP host |
| `SEED_SPEECH_ASR_POLL_INTERVAL_SECONDS` | `3.0` | Seconds between ASR query polls |
| `SEED_SPEECH_ASR_POLL_MAX_SECONDS` | `600.0` | Maximum total seconds to wait for ASR result |

JWT tool scope for speech-to-text:

- `seed:asr:transcribe`

## Object storage (TOS or S3, optional)

The `media_upload` and `media_presign` tools are registered when the selected
object-storage backend is configured. `media_upload` uploads media to a
**private** bucket and returns a presigned HTTPS GET URL; `media_presign`
generates a fresh presigned URL for an existing object without re-uploading.
Use `OBJECT_STORAGE_BACKEND` to select `tos` (default) or `s3`.

### TOS backend

| Variable | Default | Purpose |
|---|---|---|
| `TOS_ACCESS_KEY` | empty | TOS access key (AK) |
| `TOS_SECRET_KEY` | empty | TOS secret key (SK) |
| `TOS_SECURITY_TOKEN` | empty | Optional temporary security token |
| `TOS_BUCKET` | empty | Target bucket name |
| `TOS_REGION` | `ap-southeast-1` | TOS region |
| `TOS_ENDPOINT` | `tos-ap-southeast-1.bytepluses.com` | TOS API endpoint |
| `TOS_PRESIGN_TTL_SECONDS` | `1800` | Presigned URL validity in seconds (60–604800) |

### S3 backend

| Variable | Default | Purpose |
|---|---|---|
| `S3_ACCESS_KEY` | empty | S3 access key ID |
| `S3_SECRET_KEY` | empty | S3 secret access key |
| `S3_BUCKET` | empty | Target bucket name |
| `S3_REGION` | `us-east-1` | AWS region |
| `S3_ENDPOINT` | empty | Custom endpoint for S3-compatible storage (MinIO, R2) |
| `S3_PRESIGN_TTL_SECONDS` | `1800` | Presigned URL validity in seconds (60–604800) |
| `OBJECT_STORAGE_BACKEND` | `tos` | Select active backend: `tos` or `s3` |

AK and SK must both be set or both be empty. The bucket must remain private;
presigned URLs grant temporary read access to individual objects. When
`S3_ENDPOINT` is set, path-style addressing is used automatically for
S3-compatible storage.

## Persistence and runtime policy

| Variable | Default | Purpose |
|---|---|---|
| `ARTIFACT_BACKEND` | `filesystem` | Only implemented backend |
| `ARTIFACT_DIR` | `~/.modelark-mcp/artifacts` | Media, metadata, ownership, and budget state |
| `ARTIFACT_TTL_SECONDS` | `604800` | Artifact retention, in seconds |
| `MCP_INLINE_MEDIA_MAX_BYTES` | `8388608` | Maximum inline MCP media size |
| `PROVIDER_MAX_CONCURRENCY` | `5` | Process-wide slots per provider |
| `PRINCIPAL_MAX_CONCURRENCY` | `3` | Shared slots per authenticated principal |
| `DAILY_BUDGET_USD` | `0` | Per-principal UTC daily estimate limit; zero records only |
| `PERSISTENCE_CACHE_MAX_SIZE` | `10000` | Max cached provider task IDs in artifact-resolution cache |
| `PERSISTENCE_CACHE_TTL_SECONDS` | `86400` | TTL for cached task-to-artifact mappings (seconds) |

The filesystem backend enforces principal and tenant ownership. It is suitable
for one process. Multiple replicas require shared artifact, task-ownership,
budget, cache, and limiter implementations before horizontal scaling is safe.

## Timeouts and logging

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_CONNECT_TIMEOUT_MS` | `10000` | Provider connection timeout |
| `BYTEPLUS_REQUEST_TIMEOUT_MS` | `600000` | Full provider request timeout |
| `MODELARK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

Logs are structured JSON on stderr. Provider credentials and sensitive media
fields are redacted.
