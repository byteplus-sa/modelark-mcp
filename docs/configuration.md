# Configuration

All configuration is loaded from environment variables or a `.env` file using
Pydantic Settings. Copy `.env.example` to `.env` and fill in your values.

## Provider Credentials

| Variable | Description | Required |
|---|---|---|
| `BYTEPLUS_MODELARK_API_KEY` | ModelArk API key (Seedream + Seedance). Uses Bearer auth. | For image/video tools |
| `BYTEPLUS_SEED_AUDIO_API_KEY` | Seed Speech API key (Seed Audio). Uses X-Api-Key. | For audio tools |

Credentials are startup configuration only — never tool arguments. If a
credential is absent, the server does not register that product's tools.

## Provider Base URLs

| Variable | Default | Description |
|---|---|---|
| `BYTEPLUS_MODELARK_BASE_URL` | `https://ark.ap-southeast.bytepluses.com/api/v3` | ModelArk data-plane host |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech host |

API keys are region-scoped. Ensure the base URL matches your key's region.

## Model Bindings

| Variable | Default | Description |
|---|---|---|
| `SEEDREAM_DEFAULT_MODEL` | `dola-seedream-5-0-pro-260628` | Seedream model ID |
| `SEEDANCE_DEFAULT_MODEL` | `dreamina-seedance-2-0-260128` | Seedance model ID |

Model IDs are configuration, not hard-coded truth. Confirm your account's
authorized model IDs in the BytePlus console. The capability registry
validates parameters against the selected model's capabilities.

## MCP Transport

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `MCP_PORT` | `3000` | HTTP port |
| `MCP_ALLOWED_ORIGINS` | (empty) | Comma-separated allowed Origin values |

For local use, keep `stdio`. For remote deployment, use `http` with
`127.0.0.1` binding and a reverse proxy with TLS.

## Artifact Persistence

| Variable | Default | Description |
|---|---|---|
| `ARTIFACT_BACKEND` | `filesystem` | `filesystem` (local) or `object-store` (remote) |
| `ARTIFACT_DIR` | `.artifacts` | Directory for filesystem storage |
| `ARTIFACT_TTL_SECONDS` | `604800` (7 days) | How long artifacts are retained |
| `MCP_INLINE_MEDIA_MAX_BYTES` | `8388608` (8 MiB) | Max size for inline MCP content blocks |

Provider URLs expire (2h for audio, 24h for image/video). The server
persists outputs immediately into durable storage and returns
`seed-media://artifacts/{id}` resource references.

## HTTP Timeouts

| Variable | Default | Description |
|---|---|---|
| `BYTEPLUS_CONNECT_TIMEOUT_MS` | `10000` (10s) | TCP connection timeout |
| `BYTEPLUS_REQUEST_TIMEOUT_MS` | `300000` (5 min) | Full request timeout |

The 5-minute request timeout covers long synchronous generations (Seedream
Pro, Seed Audio with long text).
