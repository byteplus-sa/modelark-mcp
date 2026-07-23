# Security

This document consolidates the server's security model. See
[configuration.md](configuration.md) for the full env-var reference,
[transports.md](transports.md) for transport setup, and
[deployment.md](deployment.md) for remote-deployment hardening.

## Auth modes

`AuthMode` (`config/env.py`) is a `StrEnum`: `LOCAL = "local"` and
`JWT = "jwt"`.

| Mode | Transport | Behavior |
|---|---|---|
| `local` (default) | `stdio` or loopback HTTP | No FastMCP auth provider; a single trusted principal `local`. |
| `jwt` | HTTP (required for non-loopback) | `fastmcp.server.auth.JWTVerifier` with `ssrf_safe=True`. |

`build_auth_provider` returns `None` for `LOCAL`, and a `JWTVerifier` for
`JWT`. **Fail-closed is structural and startup-time:** if
`MCP_TRANSPORT=http` + `MCP_AUTH_MODE=local` + `MCP_HOST` is not in
`{127.0.0.1, ::1, localhost}`, `Settings` construction raises
`ValueError("HTTP on a non-loopback host requires MCP_AUTH_MODE=jwt.")` and
the server never starts.

## JWT verification

The verifier is constructed with these settings (all required in JWT mode):

| Field | Env var | Constraint |
|---|---|---|
| `jwks_uri` | `MCP_JWT_JWKS_URI` | must be `https://` with a hostname |
| `issuer` | `MCP_JWT_ISSUER` | non-empty |
| `audience` | `MCP_JWT_AUDIENCE` | non-empty |
| `ssrf_safe` | — | hard-coded `True` |

### Principal and tenant extraction

`get_principal(ctx)` (`runtime.py`) resolves the principal identity from the
verified token:

- **`sub` claim → `token.subject` → `token.client_id`** (first truthy `str`
  wins). Missing → `PermissionError("The access token is missing a principal identity.")`.
- **Tenant** is read from the claim named by `MCP_TENANT_CLAIM` (default
  `"tenant_id"`). Missing/non-string → `PermissionError`.
- A missing token → `PermissionError("An authenticated access token is required.")`.

There is **no anonymous remote principal** — JWT mode fails closed. The only
way to get an `is_local` principal (`principal_id == "local"`) is `LOCAL`
mode, which returns `PrincipalContext()` untouched (`local`/`local`, empty
scopes, `transport="stdio"`).

### `PrincipalContext` / `AuthContext`

A frozen Pydantic model (`security/auth_context.py`):

| Field | Type | Default |
|---|---|---|
| `principal_id` | `str` | `"local"` |
| `tenant_id` | `str` | `"local"` |
| `scopes` | `frozenset[str]` | `frozenset()` |
| `transport` | `Literal["stdio", "http"]` | `"stdio"` |

`is_local` returns `principal_id == "local"`. `AuthContext` is a
compatibility alias for `PrincipalContext`.

## Scope taxonomy

`component_auth(settings, *scopes)` returns `None` in `LOCAL` mode, or
`require_scopes(*scopes)` (a FastMCP `AuthCheck`) in JWT mode. The
tool → scope mapping is wired in `server.py::register_tools`:

| Scope | Protects |
|---|---|
| `seed:audio:generate` | `seed_audio_generate`, `seed_audio_generate_variations` |
| `seedream:generate` | `seedream_generate_image`, `seedream_generate_image_variations` |
| `seedance:create` | `seedance_create_task`, `seedance_create_task_variations` |
| `seedance:read` | `seedance_get_task`, `seedance_list_tasks` |
| `seedance:delete` | `seedance_cancel_or_delete_task` |
| `artifacts:read` | MCP resource `seed-media://artifacts/{artifact_id}` |

The `seed-health://status` resource and the `/health`, `/ready`, `/metrics`
routes are **not** scope-protected at the FastMCP layer. Seed Audio tools are
registered only when `BYTEPLUS_SEED_AUDIO_API_KEY` is set; Seedream/Seedance
tools only when `BYTEPLUS_MODELARK_API_KEY` is set.

## Host / Origin protection

Enabled in `__main__.py` for HTTP transport via FastMCP-native guards
(`host_origin_protection=True` plus `allowed_hosts`/`allowed_origins`). This
is **not** a custom middleware in this repo.

| Env var | Default | Notes |
|---|---|---|
| `MCP_ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1]` | comma-separated |
| `MCP_ALLOWED_ORIGINS` | `""` (empty → all browser origins rejected) | each must be an `http`/`https` URL with a hostname |

When deploying behind a public hostname, set **both** the public hostname
(in `MCP_ALLOWED_HOSTS`) and the allowed browser origins (in
`MCP_ALLOWED_ORIGINS`).

## Body-limit middleware (`security/http_middleware.py`)

`RequestBodyLimitMiddleware` (ASGI) — the only custom ASGI middleware
shipped in `security/`. Wired for HTTP transport only.

| Env var | Default | Notes |
|---|---|---|
| `MCP_HTTP_MAX_BODY_BYTES` | `10_485_760` (10 MiB), `ge=1` | rejects oversized bodies |

Behavior: reads `Content-Length`; if `> max_bytes` → `413 "Request body too
large"`; on unparseable `Content-Length` → `400`. It also wraps `receive` to
enforce the limit on streamed bodies; if the response has already started,
it re-raises `RequestBodyTooLarge` (the connection errors out rather than
sending a clean 413 mid-stream).

## SSRF-safe downloader (`security/safe_downloader.py`)

`SafeDownloader` downloads provider media (for `copy_from_trusted_url`) with
two-layer SSRF defense. Constructor defaults: `timeout=120.0s`,
`connect_timeout=30.0s`, `follow_redirects=False`, `trust_env=False`
(ignores `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`).

`download(url, *, trusted_hosts, max_bytes, max_redirects=5)`:

1. `validate_url(current_url)` — full SSRF validation (scheme, host, DNS,
   IP-class denial) returns pinned public IPs.
2. If `not trusted_hosts(hostname)` → `ValueError` (an application host
   allowlist on top of the IP-level check).
3. `_request_pinned(validated, max_bytes=...)` — **IP pinning**: connects to
   `validated.addresses[0]` while preserving the original `Host` header and
   TLS SNI (`sni_hostname`), preventing DNS rebinding between validation and
   connection. The connect URL replaces the netloc with the IP literal
   (IPv6 bracketed).
4. Redirects are handled hop-by-hop: each `Location` is revalidated from
   scratch (DNS + IP + host policy all re-applied). Missing `Location` →
   `ValueError`; too many redirects → `ValueError`.
5. **Streaming size cap:** if `Content-Length > max_bytes` → `ValueError`;
   chunks are accumulated and checked against `max_bytes` after each
   `extend`.

`FilesystemArtifactStore` restricts `copy_from_trusted_url` to provider hosts
via suffix allowlist: `.bytepluses.com`, `.byteplus.com`, `.bytedance.com`,
`.bytednsdoc.com`, `.volces.com`, `.tos-ap-southeast.bytepluses.com`.

## URL policy (`security/url_policy.py`)

Exception: `UrlValidationError(ValueError)`.

- **Blocked hostnames (literal):** `169.254.169.254` (AWS metadata),
  `metadata.google.internal` (GCP), `100.100.100.200` (Alibaba),
  `fd00:ec2::254` (AWS IPv6 metadata).
- **Allowed schemes:** `https` always; `http` only when the caller passes
  `allow_http=True`. `file://` is never allowed.
- **No credentials in URLs** (`userinfo` rejected).
- **Hostname** is IDNA-encoded → ASCII → lowercased.
- **Ports:** any explicit port is accepted syntactically; there is no
  per-port allowlist. Default is 443 (https) / 80 (http).
- **DNS + IP denial:** `resolve_public_addresses` resolves the hostname
  (or uses a literal IP directly), then denies any address that is
  `is_private`, `is_loopback`, `is_link_local`, `is_multicast`,
  `is_reserved`, or `is_unspecified`. For IPv6, embedded IPv4 transition
  formats (`ipv4_mapped`, `sixtofour`, `teredo[1]`) are recursively checked.

`validate_url` combines syntax validation + DNS resolution and returns a
`ValidatedUrl(url, parsed, hostname, port, addresses)`.

## Media policy (`security/media_policy.py`)

Exception: `MediaValidationError(ValueError)`.

`MediaLimits` (returned by `get_media_limits()`, no env override in this
module) cap **provider-bound** media:

| Limit | Default |
|---|---|
| `audio_max_bytes` | 10 MiB |
| `audio_max_seconds` | 30 |
| `image_max_bytes` | 10 MiB |
| `video_max_bytes` | 200 MiB |

Allowed MIME types:

| Category | MIME types |
|---|---|
| Audio | `audio/wav`, `audio/x-wav`, `audio/wave`, `audio/mpeg`, `audio/mp3`, `audio/pcm`, `audio/x-pcm`, `audio/ogg`, `audio/ogg;codecs=opus`, `audio/webm` |
| Image | `image/jpeg`, `image/jpg`, `image/png`, `image/webp` |
| Video | `video/mp4`, `video/quicktime` |

`check_base64_size` estimates decoded size as `(len(stripped) * 3) // 4`
(without full decode); `decode_base64_safely` validates then decodes.

> `MCP_INLINE_MEDIA_MAX_BYTES` (default 8 MiB) lives in `config/env.py`, not
> here. It caps **inline MCP media returned to the client**; the per-type
> `MediaLimits` above cap **provider-bound** media. The two are independent.

## TLS and provider URLs

- `truststore.inject_into_ssl()` runs at module import in `server.py` and
  `__main__.py`, so Python uses the macOS Keychain for TLS verification.
- Provider base URLs (`BYTEPLUS_MODELARK_BASE_URL`,
  `BYTEPLUS_SEED_AUDIO_BASE_URL`) are validated at settings load: must be
  `https://` with a hostname and no embedded credentials; trailing slash
  stripped.

## Settings caching

`get_settings()` is `@lru_cache(maxsize=1)`; `refresh_settings()` clears the
cache. Any auth/host/scope-related env change requires a process restart or
an explicit `refresh_settings()` call to take effect.
