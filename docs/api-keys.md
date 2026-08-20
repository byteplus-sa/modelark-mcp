# API Keys Guide

This server calls several BytePlus services. Each uses a distinct credential
and auth scheme — they are **not interchangeable**. You only need the keys for
the products you want to use; absent credentials simply skip registering that
tool set.

| Service | Env var | Auth header | Tools it enables |
|---|---|---|---|
| ModelArk | `BYTEPLUS_MODELARK_API_KEY` | `Authorization: Bearer <key>` | Seedream (image), Seedance (video) |
| Seed Speech (TTS) | `BYTEPLUS_SEED_AUDIO_API_KEY` | `X-Api-Key: <key>` | Seed Audio (speech generation) |
| Seed Speech (STT) | `SEED_SPEECH_ASR_API_KEY` | `X-Api-Key: <key>` | Speech-to-Text (ASR) |
| VOD AI MediaKit | `BYTEPLUS_VOD_MEDIAKIT_API_KEY` | `Authorization: Bearer <key>` | `vod_enhance_video`, `vod_transcode_video`, `vod_get_transcode_task` |
| VOD OpenAPI | `BYTEPLUS_VOD_ACCESS_KEY_ID` + `BYTEPLUS_VOD_SECRET_ACCESS_KEY` | HMAC-SHA256 request signing | `vod_separate_audio`, `vod_get_audio_separation` |
| TOS | `TOS_ACCESS_KEY` + `TOS_SECRET_KEY` + `TOS_BUCKET` | AK/SK signing | `media_upload`, `media_presign` |
| S3 | `S3_ACCESS_KEY` + `S3_SECRET_KEY` + `S3_BUCKET` | AK/SK signing | `media_upload`, `media_presign` |

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
TTS). It is a **separate key** from ModelArk and uses a different auth
header (`X-Api-Key`, not Bearer).

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_SEED_AUDIO_API_KEY` | empty | Seed Speech API key (TTS) |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech host |

**How to get the key:**

1. Sign in to **<https://console.byteplus.com>**.
2. Open **BytePlus Voice** (or Seed Speech / Speech Studio).
3. Navigate to API key or application management and create a key.
4. Copy the key. It is distinct from your ModelArk key.

```dotenv
BYTEPLUS_SEED_AUDIO_API_KEY=your-seed-audio-key-here
```

## Seed Speech ASR (Speech-to-Text)

Speech-to-text (ASR) uses a **dedicated** `SEED_SPEECH_ASR_API_KEY`, distinct
from the TTS key. If the key is set, the `speech_to_text` tool is registered
automatically — it submits audio via HTTP, polls until transcription is
complete, and returns the full `TranscriptionResult` in a single synchronous
call.

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `SEED_SPEECH_ASR_API_KEY` | empty | Seed Speech ASR API key (distinct from TTS key) |
| `SEED_SPEECH_ASR_BASE_URL` | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech ASR HTTP host |
| `SEED_SPEECH_ASR_POLL_INTERVAL_SECONDS` | `3.0` | Seconds between ASR query polls |
| `SEED_SPEECH_ASR_POLL_MAX_SECONDS` | `600.0` | Maximum total seconds to wait for ASR result |

**How to get the key:**

The ASR key is obtained from the same BytePlus Voice / Seed Speech console as
the TTS key, but is a separate credential. Set `SEED_SPEECH_ASR_API_KEY` in
`.env` to enable the `speech_to_text` tool.

## BytePlus VOD (AI MediaKit and OpenAPI)

BytePlus VOD uses **two distinct credentials** for two different surfaces:

- **VOD AI MediaKit** — a Bearer-authenticated convenience endpoint for video
  enhancement and transcoding.
- **VOD OpenAPI** — the signature-authenticated OpenAPI
  (`vod.byteplusapi.com`) used for voice and background audio separation.

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `BYTEPLUS_VOD_MEDIAKIT_API_KEY` | empty | VOD AI MediaKit Bearer key |
| `BYTEPLUS_VOD_MEDIAKIT_BASE_URL` | `https://mediakit.ap-southeast-1.bytepluses.com/api/v1` | MediaKit base URL |
| `BYTEPLUS_VOD_ACCESS_KEY_ID` | empty | VOD OpenAPI Access Key (AK) |
| `BYTEPLUS_VOD_SECRET_ACCESS_KEY` | empty | VOD OpenAPI Secret Access Key (SK) |
| `BYTEPLUS_VOD_BASE_URL` | `https://vod.byteplusapi.com` | VOD OpenAPI endpoint |
| `BYTEPLUS_VOD_REGION` | `ap-southeast-1` | VOD OpenAPI signing region |
| `BYTEPLUS_VOD_PLAYBACK_DOMAIN` | empty | Optional playback domain for output audio URLs |

**How to get the keys:**

1. Sign in to **<https://console.byteplus.com>** and enable BytePlus VOD.
2. For the MediaKit key, obtain the convenience-endpoint API key from the VOD
   AI MediaKit console area.
3. For the OpenAPI keys, open **IAM** > **Key Management** and create an Access
   Key pair (AK + SK). Copy both immediately — the SK is shown once.

The VOD OpenAPI requests are signed with HMAC-SHA256 using the AK/SK pair. The
secret key is startup configuration only and is never logged, returned, or
accepted as a tool argument.

## Object storage (TOS or S3)

Object storage is **optional** but enables several workflows: the `media_upload`
and `media_presign` tools and Seedance video references (URL-only). It uses
Access Key / Secret Key (AK/SK) signing, not a bearer token. Select the backend with
`OBJECT_STORAGE_BACKEND` (`tos` default, or `s3`).

### TOS backend

**Env vars:**

| Variable | Default | Purpose |
|---|---|---|
| `TOS_ACCESS_KEY` | empty | Access Key (AK) |
| `TOS_SECRET_KEY` | empty | Secret Key (SK) |
| `TOS_SECURITY_TOKEN` | empty | Optional temporary token (STS only) |
| `TOS_BUCKET` | empty | Target bucket name |
| `TOS_REGION` | `ap-southeast-1` | Bucket region |
| `TOS_ENDPOINT` | `tos-ap-southeast-1.bytepluses.com` | TOS API endpoint |
| `TOS_PRESIGN_TTL_SECONDS` | `1800` | Presigned URL validity in seconds (60–604800) |

`TOS_ACCESS_KEY` and `TOS_SECRET_KEY` must **both** be set or **both** be
empty. All three of AK, SK, and bucket must be set to register the
`media_upload` and `media_presign` tools.

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
  generates short-lived presigned GET URLs (default 30 minutes, configurable via
  `TOS_PRESIGN_TTL_SECONDS`) for individual objects.
- Uploaded objects are **not auto-deleted** by this server. Configure a TOS
  bucket lifecycle rule to expire objects under the upload prefixes
  (`stt-input/`, `references/`) to control storage cost over time.
- For temporary credentials (STS), also set `TOS_SECURITY_TOKEN`.

### S3 backend

| Variable | Default | Purpose |
|---|---|---|
| `S3_ACCESS_KEY` | empty | S3 access key ID |
| `S3_SECRET_KEY` | empty | S3 secret access key |
| `S3_BUCKET` | empty | Target bucket name |
| `S3_REGION` | `us-east-1` | AWS region |
| `S3_ENDPOINT` | empty | Custom endpoint for S3-compatible storage |
| `S3_PRESIGN_TTL_SECONDS` | `1800` | Presigned URL validity in seconds (60–604800) |
| `OBJECT_STORAGE_BACKEND` | `tos` | Select active backend: `tos` or `s3` |

`S3_ACCESS_KEY` and `S3_SECRET_KEY` must **both** be set or **both** be
empty. All three of AK, SK, and bucket must be set to register the
`media_upload` and `media_presign` tools with the S3 backend.

When `S3_ENDPOINT` is set, path-style addressing is used automatically for
S3-compatible storage (MinIO, R2, TOS-via-boto3).

## Verifying your setup

After filling in `.env`, start the server and check the health resource — it
reports which providers are configured:

```bash
make dev
```

The `seed-health://status` MCP resource reports `ModelArk configured`,
`Seed Audio configured`, `STT configured`, `TOS configured`, `S3 configured`,
and `Object storage backend` values per
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

# Seed Speech — TTS
BYTEPLUS_SEED_AUDIO_API_KEY=
BYTEPLUS_SEED_AUDIO_BASE_URL=https://voice.ap-southeast-1.bytepluses.com

# Seed Speech ASR — STT
SEED_SPEECH_ASR_API_KEY=
SEED_SPEECH_ASR_BASE_URL=https://voice.ap-southeast-1.bytepluses.com
SEED_SPEECH_ASR_POLL_INTERVAL_SECONDS=3.0
SEED_SPEECH_ASR_POLL_MAX_SECONDS=600.0

# BytePlus VOD — AI MediaKit (Bearer)
BYTEPLUS_VOD_MEDIAKIT_API_KEY=
BYTEPLUS_VOD_MEDIAKIT_BASE_URL=https://mediakit.ap-southeast-1.bytepluses.com/api/v1

# BytePlus VOD — OpenAPI (AK/SK signature)
BYTEPLUS_VOD_ACCESS_KEY_ID=
BYTEPLUS_VOD_SECRET_ACCESS_KEY=
BYTEPLUS_VOD_BASE_URL=https://vod.byteplusapi.com
BYTEPLUS_VOD_REGION=ap-southeast-1
BYTEPLUS_VOD_PLAYBACK_DOMAIN=

# Object storage — TOS (optional, default backend)
TOS_ACCESS_KEY=
TOS_SECRET_KEY=
TOS_BUCKET=
TOS_REGION=ap-southeast-1
TOS_ENDPOINT=tos-ap-southeast-1.bytepluses.com
TOS_PRESIGN_TTL_SECONDS=1800

# Object storage — S3 (optional alternative backend)
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET=
S3_REGION=us-east-1
S3_ENDPOINT=
S3_PRESIGN_TTL_SECONDS=1800
OBJECT_STORAGE_BACKEND=tos
```

Console: **<https://console.byteplus.com>**
Docs: **<https://docs.byteplus.com>**
