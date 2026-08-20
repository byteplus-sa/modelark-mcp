---
title: BytePlus VOD OpenAPI Provider Contract
type: spec
status: accepted
horizon: current
created: 2026-08-19
updated: 2026-08-19
source:
  - https://docs.byteplus.com/en/docs/byteplus-vod/docs-voice-background-audio-separation
  - https://docs.byteplus.com/en/docs/byteplus-vod/reference-startexecution
  - https://docs.byteplus.com/en/docs/byteplus-vod/reference-getexecution
  - https://docs.byteplus.com/en/docs/byteplus-platform/reference-how-to-calculate-a-signature
related:
  - plans/PLAN_BYTEPLUS_VOD_AUDIO_SEPARATION.md
  - specs/SPEC_VOD_MEDIAKIT_PROVIDER_CONTRACT.md
---

<!-- markdownlint-disable MD013 -->

# BytePlus VOD OpenAPI Provider Contract

This spec is the source of truth for the signature-authenticated BytePlus VOD
OpenAPI surface used by `vod_separate_audio` / `vod_get_audio_separation`. It is
distinct from the Bearer-authenticated AI MediaKit convenience surface
(`specs/SPEC_VOD_MEDIAKIT_PROVIDER_CONTRACT.md`).

## Auth

- Endpoint: `https://vod.byteplusapi.com` (region-scoped; endpoint host is
  region-agnostic but the signing region matters).
- Credentials: `BYTEPLUS_VOD_ACCESS_KEY_ID` (AK) and
  `BYTEPLUS_VOD_SECRET_ACCESS_KEY` (SK). SK is never logged, returned, or
  accepted as a tool argument.
- Version: `2025-07-01`.
- Service name in credential scope: `vod`.

Signing (BytePlus OpenAPI v4, HMAC-SHA256 only):

1. `X-Date` = UTC `YYYYMMDDTHHMMSSZ`; `ShortDate` = `YYYYMMDD`.
2. `X-Content-Sha256` = hex SHA-256 of the request body (empty string for GET).
3. Canonical headers (lowercased, ASCII-sorted, trimmed): POST signs
   `content-type;host;x-content-sha256;x-date`; GET signs
   `host;x-content-sha256;x-date`.
4. `CanonicalRequest = METHOD + "\n" + "/" + "\n" + CanonicalQueryString + "\n"
   + CanonicalHeaders + "\n" + SignedHeaders + "\n" + HexEncode(Hash(Payload))`.
   The canonical query string is the sorted, RFC3986-percent-encoded
   `key=value` pairs.
5. `CredentialScope = {ShortDate}/{region}/vod/request`.
6. `StringToSign = "HMAC-SHA256\n" + X-Date + "\n" + CredentialScope + "\n" +
   HexEncode(Hash(CanonicalRequest))`.
7. Signing key: `HMAC(HMAC(HMAC(HMAC(SK, ShortDate), region), "vod"), "request")`.
8. `Authorization: HMAC-SHA256 Credential={AK}/{CredentialScope},
   SignedHeaders={SignedHeaders}, Signature={HexEncode(HMAC(key, StringToSign))}`.

## Submit — `POST /?Action=StartExecution&Version=2025-07-01`

Request body (PascalCase; `extra=forbid` on outbound DTOs):

```json
{
  "Input": {
    "Type": "DirectUrl",
    "DirectUrl": {
      "FileName": "path/to/source.mp4",
      "SpaceName": "my-space",
      "BucketName": "tos-vod-bucket"
    }
  },
  "Operation": {
    "Type": "Task",
    "Task": {
      "Type": "AudioExtract",
      "AudioExtract": {
        "Voice": true,
        "AudioOption": { "Format": "aac" }
      }
    }
  }
}
```

- Only DirectUrl input mode is exposed. `FileName` is required; `SpaceName` and
  `BucketName` are optional. A public HTTPS URL is **not** accepted.
- `AudioExtract.Voice = true`; `AudioOption.Format = "aac"` (only `aac` is
  confirmed).
- Response: `{ "ResponseMetadata": { "RequestId", ... }, "Result": { "RunId" } }`.

## Poll — `GET /?Action=GetExecution&Version=2025-07-01&RunId=<run_id>`

Response:

```json
{
  "ResponseMetadata": { "RequestId", ... },
  "Result": {
    "RunId": "...",
    "Status": "Success",
    "Output": {
      "Type": "Task",
      "Task": {
        "Type": "AudioExtract",
        "AudioExtract": {
          "Duration": 107.90168,
          "Voice": { "FileName": "..._audiospeech.aac", "Size": "1787924" },
          "Background": { "FileName": "..._background.aac", "Size": "1787924" }
        }
      }
    }
  }
}
```

- `Size` is a numeric string in the sample but may be numeric; the adapter
  accepts `int`/`float`/digit-string and normalizes to `int | None` bytes.
- `Status` normalization:
  - `Success` → `succeeded` (requires `Voice.FileName`; missing → `INVALID_RESPONSE`).
  - `Fail` / `Failed` / `Error` / `Terminated` / `Timeout` → `failed` (failure
    code taken from `Result.Code` when present, else `FAILED`).
  - Any other non-empty value → `processing` (raw label preserved).
  - Empty/missing → `INVALID_RESPONSE`.

## Error envelope

Non-2xx responses carry `ResponseMetadata.Error` with `Code` (string) or `CodeN`
(numeric) and `Message`. The gateway normalizes these to `NormalizedProviderError`
with `provider = "byteplus-vod"`, the `RequestId`, 429 → `retryable`, and
5xx → `ambiguous_completion`.

## Output resolution

Outputs are VOD storage `FileName` paths, not direct URLs. The poll tool returns
each track's `file_name`, `size_bytes`, and an optional
`https://{playback_domain}/{file_name}` URL when a playback domain is supplied
per call or via `BYTEPLUS_VOD_PLAYBACK_DOMAIN` (bare hostname only). Outputs are
not copied into the local artifact store.

## Unverified contract points

- The full `Status` enum for `GetExecution` beyond `Success`/failure labels is
  not published; failure/processing mapping is defensive.
- The `Input.DirectUrl` object mirrors `StartWorkflow`'s DirectUrl
  (`FileName`/`SpaceName`/`BucketName`) — confirmed indirectly, not from a
  rendered StartExecution reference page.
- Output URL signing (hotlink protection `auth_key`) is not implemented; clients
  with URL signing enabled must compute signed URLs themselves.
