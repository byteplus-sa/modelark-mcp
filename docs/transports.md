# Transports

The server supports two transports, both natively supported by FastMCP.

## stdio (default, local)

The default transport for local deployment. MCP JSON-RPC messages flow
over stdin/stdout. Structured logs go to stderr — only JSON-RPC goes to
stdout, as required by the MCP specification.

```bash
make start
# or
uv run python -m modelark_mcp
```

Use this mode with:

- Claude Desktop
- MCP Inspector
- Any MCP client that spawns the server as a subprocess

## Streamable HTTP (remote deployment)

For remote or networked deployment. Binds to `127.0.0.1` by default to
prevent DNS rebinding attacks. Use a reverse proxy (nginx, Caddy) with
TLS in front.

```bash
make start-http
# or
MCP_TRANSPORT=http uv run python -m modelark_mcp
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `MCP_HOST` | `127.0.0.1` | Bind address |
| `MCP_PORT` | `3000` | Listen port |
| `MCP_ALLOWED_ORIGINS` | (empty) | Comma-separated Origin allowlist |

### Security Notes

For remote multi-tenant deployment, you need:

- **OAuth resource-server middleware** — validate JWT audience/issuer/scopes
- **Origin validation** — reject requests with invalid `Origin` headers
- **Rate limiting** — per-principal concurrency and request limits
- **HTTPS** — TLS termination via reverse proxy
- **Scope checks** — suggested scopes: `seed:audio:generate`,
  `seedream:generate`, `seedance:create`, `seedance:read`, `seedance:delete`

These are not yet implemented — the server is designed for local `stdio`
use first. Remote hardening is a planned follow-up.

## MCP Inspector

Launch the FastMCP inspector to explore tools, resources, and schemas
interactively:

```bash
make inspect
# or
make inspect-dev   # with auto-reload
```

The inspector connects over `stdio` and provides a web UI for testing tool
calls, viewing input/output schemas, and browsing resources.
