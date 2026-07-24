# Configuration

Configuration is loaded from environment variables or `.env` by Pydantic
Settings. Copy `.env.example` to `.env`. Empty values are ignored.

## Providers and models

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_MODELARK_API_KEY` | empty | Enables Seedream and Seedance; sent as Bearer auth |
| `BYTEPLUS_SEED_AUDIO_API_KEY` | empty | Enables Seed Audio; sent as `X-Api-Key` |
| `BYTEPLUS_MODELARK_BASE_URL` | AP Southeast ModelArk URL | HTTPS data-plane base URL |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | AP Southeast Seed Speech URL | HTTPS service base URL |
| `SEEDREAM_DEFAULT_MODEL` | `dola-seedream-5-0-pro-260628` | Default image model/endpoint ID |
| `SEEDANCE_DEFAULT_MODEL` | `dreamina-seedance-2-0-260128` | Default video model/endpoint ID |
| `SEEDREAM_MODEL_FAMILY` | empty | Family for a custom default: `pro`, `lite`, or `4x` |
| `SEEDANCE_MODEL_FAMILY` | empty | Family for a custom default: `standard`, `fast`, or `mini` |
| `SEEDREAM_MODEL_BINDINGS` | empty | JSON list of `{model_id, family}` bindings |
| `SEEDANCE_MODEL_BINDINGS` | empty | JSON list of `{model_id, family}` bindings |

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
- `media:upload`
- `artifacts:read`

## TOS object storage (optional)

The `media_upload` tool is registered only when all three of `TOS_ACCESS_KEY`,
`TOS_SECRET_KEY`, and `TOS_BUCKET` are set. It uploads media to a **private**
bucket and returns a presigned HTTPS GET URL.

| Variable | Default | Purpose |
|---|---|---|
| `TOS_ACCESS_KEY` | empty | TOS access key (AK) |
| `TOS_SECRET_KEY` | empty | TOS secret key (SK) |
| `TOS_SECURITY_TOKEN` | empty | Optional temporary security token |
| `TOS_BUCKET` | empty | Target bucket name |
| `TOS_REGION` | `ap-southeast-1` | TOS region |
| `TOS_ENDPOINT` | `tos-ap-southeast-1.bytepluses.com` | TOS API endpoint |
| `TOS_PRESIGN_TTL_SECONDS` | `86400` | Presigned URL validity (60–604800) |

AK and SK must both be set or both be empty. The bucket must remain private;
presigned URLs grant temporary read access to individual objects.

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
