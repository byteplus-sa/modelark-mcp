## Summary

Adds BytePlus VOD **voice and background audio separation** to the MCP server
via the VOD OpenAPI (`StartExecution` with `Task.Type=AudioExtract`, polled with
`GetExecution`).

- New signature-authenticated provider `providers/vod` (BytePlus OpenAPI V4
  HMAC-SHA256 request signing).
- New submit-then-poll tool pair: `vod_separate_audio` (submit, scope
  `vod:extract`) and `vod_get_audio_separation` (poll, scope `vod:read`).
- DirectUrl (storage-path) input only; outputs `FileName`/`Size` for the vocal
  and background AAC tracks plus optional `https://{playback_domain}/{FileName}`
  URLs. Outputs stay in the VOD space (no durable local artifact persistence).

## Configuration

New env vars: `BYTEPLUS_VOD_ACCESS_KEY_ID`, `BYTEPLUS_VOD_SECRET_ACCESS_KEY`,
`BYTEPLUS_VOD_REGION` (default `ap-southeast-1`), `BYTEPLUS_VOD_BASE_URL`
(default `https://vod.byteplusapi.com`), `BYTEPLUS_VOD_PLAYBACK_DOMAIN`
(optional). Tools register only when both AK and SK are set.

## Scope decisions

- Input: **DirectUrl storage path** only — `{ file_name, space_name, bucket_name }`
  pointing at media already in the VOD space's TOS bucket. A public HTTPS URL is
  not accepted (that would need an `UploadMediaByUrl` pre-step).
- Output: `FileName` + `Size` per track, with optional playback URLs.

## Validation

- `ruff check`, `ruff format --check`, `mypy src` clean.
- Full suite: **888 passed** in a clean worktree.
- Contract/integration/conformance tests cover the signing algorithm (pinned
  fixtures), submit/poll normalization, playback-URL building, ownership, and
  error handling.

## Known limitations / follow-ups

- `GetExecution` statuses beyond `Success`/failure labels are normalized
  defensively (full enum not published).
- `Input.DirectUrl` object mirrors `StartWorkflow`'s DirectUrl; not yet
  confirmed from a rendered `StartExecution` reference page.
- Output URL signing (`auth_key` hotlink protection) is not implemented.

See `specs/SPEC_VOD_OPENAPI_PROVIDER_CONTRACT.md` and
`plans/PLAN_BYTEPLUS_VOD_AUDIO_SEPARATION.md`.
