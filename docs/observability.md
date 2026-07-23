# Observability

The server ships structured JSON logging and a Prometheus metrics endpoint.
Provider HTTP calls also emit OpenTelemetry spans, but the server does not
configure an OTel exporter — spans are no-ops unless you wire up an SDK.

## Structured logging (`observability/logger.py`)

- **Output:** one JSON object per line, written to **stderr**. stdout is
  reserved for MCP JSON-RPC (stdio transport requirement).
- **Serialization:** `json.dumps(record, default=str, ensure_ascii=False)`.
  `default=str` stringifies non-JSON-native objects (UUIDs, datetimes,
  exceptions, dataclasses).

Each log line always contains:

| Field | Value |
|---|---|
| `ts` | `datetime.now(UTC).isoformat()` |
| `level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `msg` | human message |

plus any additional `**fields` passed to the helper (after redaction).

### Public API

Four module-level functions, all `(message: str, **fields: Any) -> None`:
`debug`, `info`, `warning` (emits level `"WARNING"`), `error`.

### Level control

| Env var | Default | Notes |
|---|---|---|
| `MODELARK_LOG_LEVEL` | `INFO` | recognized: `DEBUG`, `INFO`, `WARNING`, `ERROR`; an unknown value silently falls back to `INFO` |

`set_level(level)` overrides at runtime (called once from `create_server`,
which passes the resolved `Settings.log_level`); `get_level()` returns the
current name. `set_level` normalizes via `.upper()` (it does not trim
whitespace) and **raises `ValueError`** for unrecognized levels — it does
not fall back. The silent fallback to `INFO` happens only at module-import
time, where `MODELARK_LOG_LEVEL` is looked up in the level map with a
default of `20` (INFO).

Through the normal `Settings` path, `MODELARK_LOG_LEVEL` is a
`Literal["DEBUG","INFO","WARNING","ERROR"]` field with a before-validator
that uppercases; an untrimmed value such as `" info "` becomes `" INFO "`
and is rejected by Pydantic before `set_level` is ever called.

At default `INFO` (20): DEBUG is dropped; INFO/WARNING/ERROR are emitted.

### Redaction

`_redact` recursively walks dicts/lists. Any dict whose key (lowercased) is
in the redaction set is replaced with `"[REDACTED]"`. Redaction is **exact
key match**, not substring — so `user_url_custom` is NOT redacted.

Redacted keys (case-insensitive): `authorization`, `x-api-key`, `api_key`,
`apikey`, `token`, `secret`, `password`, `b64_json`, `audio_data`,
`image_data`, `base64`, `prompt`, `text_prompt`, `variation_prompts`,
`subtitle`, `subtitles`, `url`, `media_url`, `audio_url`, `image_url`,
`video_url`.

Policy (per the module docstring): never log prompt text, full media URLs,
Base64, subtitles, or credentials. Redaction is a safety net; call sites
avoid passing these fields in the first place.

## Prometheus metrics (`observability/metrics.py`)

Seven metrics total — 5 Counters + 2 Histograms. **There are no Gauges.**
Label cardinality is intentionally bounded (no tenant, model, URL, or request
labels). Both Histograms use the `prometheus_client` default buckets
`(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, +Inf)` seconds.

| Metric | Type | Labels | What it measures | Label values |
|---|---|---|---|---|
| `modelark_mcp_tool_requests_total` | Counter | `tool`, `status` | MCP tool invocations | `success`, `error`, `exception` |
| `modelark_mcp_tool_duration_seconds` | Histogram | `tool` | wall-clock duration of a tool call (observed in `finally`, even on exception) | — |
| `modelark_mcp_provider_requests_total` | Counter | `provider`, `operation`, `status` | outbound provider HTTP requests | `operation` = HTTP method lowercased; `status` = `success` (HTTP < 400) / `error` (HTTP ≥ 400) / `exception` |
| `modelark_mcp_provider_duration_seconds` | Histogram | `provider`, `operation` | provider HTTP request duration (observed in `finally`) | `operation` = HTTP method lowercased |
| `modelark_mcp_artifact_operations_total` | Counter | `operation`, `status`, `media_type` | artifact store put/get | `operation` = `put` / `get`; only `status="success"` is emitted in current call sites |
| `modelark_mcp_budget_rejections_total` | Counter | `product` | requests rejected for exceeding daily budget | one inc per rejection |
| `modelark_mcp_retry_attempts_total` | Counter | `provider`, `operation` | retried provider attempts (excluding the initial attempt) | one inc per retry |

### `MetricsMiddleware`

A FastMCP middleware that overrides **only** `on_call_tool`. It does not
intercept resource reads, list-tools, or HTTP routes. For each tool call:

1. reads `tool_name` from the request params;
2. records `perf_counter()` start;
3. `await call_next(context)`;
4. on exception → `TOOL_REQUESTS{tool, status="exception"}` then re-raise;
   on return → `status = "error" if result.is_error else "success"`;
5. in `finally` → `TOOL_DURATION{tool}.observe(elapsed)` (always recorded).

`status` here is MCP-level, not HTTP: `success` = result with `is_error=False`,
`error` = MCP error result (`is_error=True`), `exception` = Python exception.

### `/metrics` endpoint

```python
@server.custom_route("/metrics", methods=["GET"])
async def metrics(_request):
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- **Content type:** `text/plain; version=0.0.4; charset=utf-8`.
- Uses the default `prometheus_client.REGISTRY`, so it also exposes the
  built-in `process_*` (e.g. `process_resident_memory_bytes`,
  `process_open_fds`) and `python_*` metrics.
- **Auth:** this route is registered with no `auth=` argument, so it is **not
  protected** by the FastMCP auth provider. On Streamable HTTP, protect
  `/metrics` at the reverse proxy / ingress layer. `/health` and `/ready` are
  likewise unauthenticated at the FastMCP layer.

## OpenTelemetry / tracing

Spans are emitted around provider HTTP requests in `providers/base.py`:

```python
with get_tracer().start_as_current_span(f"provider.{self.PROVIDER}.{operation}") as span:
    span.set_attribute("provider.name", self.PROVIDER)
    span.set_attribute("http.request.method", method)
    ...
    span.set_attribute("http.response.status_code", response.status_code)  # success path only
```

- **Span name:** `provider.<provider>.<operation>` (e.g.
  `provider.modelark.post`, `provider.seed_speech.post`).
- **Attributes:** `provider.name`, `http.request.method`, and
  `http.response.status_code` (success path only). On exception,
  `record_span_error(span, exc)` records the exception event.
- **Scope:** spans exist **only** around provider HTTP calls through
  `BaseHttpGateway._request`. There are no spans around tool execution,
  artifact store ops, budget reservation, the retry loop, resource reads, or
  the HTTP routes.

> **No exporter configured.** `get_tracer()` returns FastMCP's tracer, which
> is a **no-op unless the operator initializes the OpenTelemetry SDK** (e.g.
> sets `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_ENDPOINT`, etc. in the
> process environment). By default the span calls execute but produce no
> exported telemetry. Wire up OTel export yourself to get spans out.

## Gaps worth knowing

- No Gauges anywhere — in-flight requests, current daily spend, stored
  artifact count, and concurrency depth are not metricated (spend is only
  observable via the SQLite ledger; in-flight only via the process metrics).
- `ARTIFACT_OPERATIONS` has a `status` label, but call sites only ever emit
  `success` (failures raise before the counter is touched).
- `/metrics`, `/health`, `/ready` are unauthenticated at the FastMCP layer —
  protect them at ingress.

See [configuration.md](configuration.md) for the related env vars and
[deployment.md](deployment.md) for probe/monitoring guidance.
