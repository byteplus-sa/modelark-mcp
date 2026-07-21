# Troubleshooting

## SSL Certificate Errors

On macOS, the uv-installed Python may not use the system Keychain for TLS
verification. If you see `CERTIFICATE_VERIFY_FAILED`, install and enable
`truststore`:

```bash
uv add truststore
```

The server already injects `truststore` at startup in `__main__.py` and
`server.py`. If running scripts that bypass the server module, add:

```python
import truststore
truststore.inject_into_ssl()
```

## "API key not configured" Error

If a tool raises `BYTEPLUS_*_API_KEY is not configured`, the server did not
find the credential in the environment. Check:

1. `.env` file exists at the project root
2. The key name matches exactly (`BYTEPLUS_MODELARK_API_KEY` or
   `BYTEPLUS_SEED_AUDIO_API_KEY`)
3. No leading/trailing whitespace in the value
4. Run `make check-env` to validate

When a credential is absent, the server skips registering that product's
tools — it does not register a broken tool.

## Model Not Found / Not Activated

If the provider returns `403 FORBIDDEN` with "model not activated":

1. Check the model ID in `.env` matches your console
2. Confirm the model is activated in your BytePlus region
3. Verify the base URL matches your key's region

Model IDs are region-scoped and account-specific. The defaults in
`.env.example` may not match your account. Use `scripts/verify_phase0.py`
to test with minimal cost.

## Provider URL Expired

Provider output URLs expire:

- **Seed Audio**: 2 hours
- **Seedream**: 24 hours
- **Seedance**: 24 hours (video and last-frame)

The server persists outputs immediately by default (`persist=True`) and
returns `seed-media://artifacts/{id}` resource references that do not
expire (until the artifact TTL, default 7 days).

If you set `persist=False`, the tool returns the raw provider URL which
will expire. Use the artifact resource instead.

## Seedance Task States

| Status | Meaning |
|---|---|
| `queued` | Task is waiting to start |
| `running` | Task is generating |
| `succeeded` | Task completed, video available |
| `failed` | Task failed, check `error` field |
| `expired` | Task expired before completion |
| `cancelled` | Task was cancelled via DELETE |

### Cannot Cancel or Delete

- `running` tasks cannot be cancelled or deleted — wait for completion
- `cancelled` tasks cannot be deleted

The `seedance_cancel_or_delete_task` tool requires `expected_status` to
match the actual status, preventing accidental destructive actions.

## Timeout on Long Generations

Seedream Pro and long Seed Audio generation can take 1-5 minutes. The
default request timeout is 5 minutes (`BYTEPLUS_REQUEST_TIMEOUT_MS=300000`).

If you experience timeouts:

1. Increase `BYTEPLUS_REQUEST_TIMEOUT_MS`
2. Check your network connectivity to the BytePlus region
3. Note: a timeout does **not** mean the operation failed — it may have
   succeeded upstream. The error is marked `ambiguous_completion=True`.
   Do not retry blindly.

## Artifacts Not Persisting

Check:

1. `ARTIFACT_DIR` is writable
2. Disk has sufficient space
3. `ARTIFACT_BACKEND` is set to `filesystem` (the only MVP backend)

Run `make check-env` to validate configuration.

## Running Tests

```bash
make test          # run all tests
make lint          # ruff check
make typecheck     # mypy
```

Tests use `respx` to mock HTTP — no real API calls are made in CI.
