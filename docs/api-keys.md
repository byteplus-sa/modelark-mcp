# API Keys Guide

This server calls four BytePlus services. Each uses a distinct credential and
auth scheme — they are **not interchangeable**. You only need the keys for the
products you want to use; absent credentials simply skip registering that
tool set.

| Service | Env var | Auth header | Tools it enables |
|---|---|---|---|
| ModelArk | `BYTEPLUS_MODELARK_API_KEY` | `Authorization: Bearer <key>` | Seedream (image), Seedance (video) |
| Seed Speech | `BYTEPLUS_SEED_AUDIO_API_KEY` | `X-Api-Key: <key>` | Seed Audio (TTS), Speech-to-Text (STT) |
| TOS | `TOS_ACCESS_KEY` + `TOS_SECRET_KEY` + `TOS_BUCKET` | AK/SK signing | `media_upload`, Base64/file upload for STT |

Copy `.env.example` to `.env` and fill in the keys you need.

```bash
cp .env.example .env
```

All keys below are **startup configuration** — they are never accepted as tool
arguments. Keep your `.env` file out of version control (it is already in
`.gitignore`).

## ModelArk

ModelArk is the data-plane host for **Seedream** (image generation/editing) and
**Seedance** (video generation). The key is sent as a Bearer token.

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_MODELARK_API_KEY` | empty | ModelArk API key |
| `BYTEPLUS_MODELARK_BASE_URL` | `https://ark.ap-southeast.bytepluses.com/api/v3` | Region-scoped data-plane host |

**How to get the key:**

1. Sign in to the BytePlus console at **<https://console.byteplus.com>**.
2. Open **ModelArk** (Ark) and navigate to **API Key** management.
3. Create a new API key. Copy it immediately — it is shown once.
4. (Optional) Create an **inference endpoint** for the Seedream or Seedance
   model you want to use, then set its ID as `SEEDREAM_DEFAULT_MODEL` or
   `SEEDANCE_DEFAULT_MODEL`. The built-in defaults already have known families;
   a custom endpoint ID must be bound via `SEEDREAM_MODEL_BINDINGS` /
   `SEEDANCE_MODEL_BINDINGS`.

```dotenv
BYTEPLUS_MODELARK_API_KEY=your-modelark-key-here
```

The base URL is region-scoped. If your account is in a different region, update
`BYTEPLUS_MODELARK_BASE_URL` to match.

## Seed Speech

Seed Speech is the service for **Seed Audio** (full-scene audio generation /
TTS) and **Speech-to-Text** (ASR). Both share the same `X-Api-Key`
credential. It is a **separate key** from ModelArk and uses a different auth
header (`X-Api-Key`, not Bearer).

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_SEED_AUDIO_API_KEY` | empty | Seed Speech API key (shared by TTS and STT) |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech host |
| `SEED_SPEECH_ASR_WS_URL` | `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel` | WebSocket endpoint for STT |

**How to get the key:**

1. Sign in to **<https://console.byteplus.com>**.
2. Open **BytePlus Voice** (or Seed Speech / Speech Studio).
3. Navigate to API key or application management and create a key.
4. Copy the key. It is distinct from your ModelArk key.

```dotenv
BYTEPLUS_SEED_AUDIO_API_KEY=your-seed-audio-key-here
```

## Seed Speech ASR (Speech-to-Text)

Speech-to-text (ASR) uses the **same** `BYTEPLUS_SEED_AUDIO_API_KEY` as Seed
Audio. There is no separate STT credential. If the key is set, the
`speech_to_text` tool is registered automatically — it opens a WebSocket to
Seed Speech ASR, streams the audio, and returns the complete transcription in a
single synchronous call.

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `SEED_SPEECH_ASR_WS_URL` | `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel` | WebSocket endpoint for streaming ASR |
| `SEED_SPEECH_ASR_RESOURCE_ID` | `volc.seedasr.sauc.duration` | Resource ID for the ASR service |
| `SEED_SPEECH_ASR_APPID` | empty | Optional BytePlus appid for the ASR config payload |
| `SEED_SPEECH_ASR_CLUSTER` | empty | Optional BytePlus cluster for the ASR config payload |
| `SEED_SPEECH_ASR_CHUNK_BYTES` | `16384` | Audio chunk size (bytes) per WS message |
| `SEED_SPEECH_ASR_MAX_DURATION_SECONDS` | `3600` | Hard cap on audio duration to bound the blocking call |

**How to get the key:**

The same Seed Speech key used for TTS also enables STT. See the Seed Speech
section above for instructions. There is no separate STT credential to obtain.

## TOS (Object Storage)

TOS is **optional** but enables several workflows: the `media_upload` tool,
Seedance video references (URL-only), and Base64/file input for speech-to-text.
It uses Access Key / Secret Key (AK/SK) signing, not a bearer token.

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `TOS_ACCESS_KEY` | empty | Access Key (AK) |
| `TOS_SECRET_KEY` | empty | Secret Key (SK) |
| `TOS_SECURITY_TOKEN` | empty | Optional temporary token (STS only) |
| `TOS_BUCKET` | empty | Target bucket name |
| `TOS_REGION` | `ap-southeast-1` | Bucket region |
| `TOS_ENDPOINT` | `tos-ap-southeast-1.bytepluses.com` | TOS API endpoint |
| `TOS_PRESIGN_TTL_SECONDS` | `86400` | Presigned URL validity (60–604800) |

`TOS_ACCESS_KEY` and `TOS_SECRET_KEY` must **both** be set or **both** be
empty. All three of AK, SK, and bucket must be set to register the
`media_upload` tool.

**How to get the keys:**

1. Sign in to **<https://console.byteplus.com>**.
2. Open **TOS** (Object Storage).
3. Create a **bucket** (keep it **private**) in your target region. Note the
   bucket name and region — set them as `TOS_BUCKET` and `TOS_REGION`.
4. For the access keys: open **IAM** (Identity and Access Management) and
   create an access key pair (AK + SK) for a user or service account that has
   read/write permission on that bucket. Copy both immediately — the SK is
   shown once.

```dotenv
TOS_ACCESS_KEY=your-access-key
TOS_SECRET_KEY=your-secret-key
TOS_BUCKET=your-private-bucket
TOS_REGION=ap-southeast-1
TOS_ENDPOINT=tos-ap-southeast-1.bytepluses.com
```

**Security notes:**

- Keep the bucket **private**. The server never makes objects public; it
  generates short-lived presigned GET URLs (default 24 hours, configurable via
  `TOS_PRESIGN_TTL_SECONDS`) for individual objects.
- Uploaded objects are **not auto-deleted** by this server. Configure a TOS
  bucket lifecycle rule to expire objects under the upload prefixes
  (`stt-input/`, `references/`) to control storage cost over time.
- For temporary credentials (STS), also set `TOS_SECURITY_TOKEN`.

## Verifying your setup

After filling in `.env`, start the server and check the health resource — it
reports which providers are configured:

```bash
make dev
```

The `seed-health://status` MCP resource reports `ModelArk configured`,
`Seed Audio configured`, `STT configured`, and `TOS configured` booleans per
provider. The separate `/health` HTTP route is a liveness probe that returns
only `{"status": "healthy"}`. Any provider reported `false` means its key was
not loaded — check the env var spelling and that the `.env` file is in the
project root.

If a tool is missing entirely, its provider credentials were absent at startup.
Tools are registered conditionally based on which keys are present.

## Quick reference

```dotenv
# ModelArk — image + video
BYTEPLUS_MODELARK_API_KEY=
BYTEPLUS_MODELARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3

# Seed Speech — TTS + STT
BYTEPLUS_SEED_AUDIO_API_KEY=
BYTEPLUS_SEED_AUDIO_BASE_URL=https://voice.ap-southeast-1.bytepluses.com

# Seed Speech ASR (STT)
SEED_SPEECH_ASR_WS_URL=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel
SEED_SPEECH_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
SEED_SPEECH_ASR_APPID=
SEED_SPEECH_ASR_CLUSTER=

# TOS — object storage (optional)
TOS_ACCESS_KEY=
TOS_SECRET_KEY=
TOS_BUCKET=
TOS_REGION=ap-southeast-1
TOS_ENDPOINT=tos-ap-southeast-1.bytepluses.com
TOS_PRESIGN_TTL_SECONDS=86400
```

Console: **<https://console.byteplus.com>**
Docs: **<https://docs.byteplus.com>**
