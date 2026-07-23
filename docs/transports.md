# Transports

The server supports stdio and FastMCP Streamable HTTP.

## stdio

stdio is the secure local default. MCP JSON-RPC uses stdin/stdout; structured
logs use stderr.

```bash
make start
# equivalent
uv run python -m modelark_mcp
```

Use this mode when an MCP client launches the server as a subprocess. The
local principal owns artifacts and Seedance tasks created by that process.

## Streamable HTTP

Loopback development can use local auth:

```bash
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 uv run python -m modelark_mcp
```

Network deployment must use JWT verification:

```bash
MCP_TRANSPORT=http \
MCP_HOST=0.0.0.0 \
MCP_AUTH_MODE=jwt \
MCP_JWT_JWKS_URI=https://id.example.com/.well-known/jwks.json \
MCP_JWT_ISSUER=https://id.example.com/ \
MCP_JWT_AUDIENCE=modelark-mcp \
MCP_ALLOWED_HOSTS=mcp.example.com \
MCP_ALLOWED_ORIGINS=https://client.example.com \
uv run python -m modelark_mcp
```

The server validates JWT signature, issuer, audience, scopes, principal, and
tenant. Host/Origin protection and a streamed body-size limit are enabled.
Terminate TLS at a trusted reverse proxy and pass the original Host header.

## Operational HTTP routes

| Route | Authentication | Meaning |
|---|---|---|
| `/health` | none | Process liveness |
| `/ready` | none | Runtime, database, and artifact-directory readiness |
| `/metrics` | none | Prometheus exposition |

Restrict `/metrics` at the network or reverse-proxy layer if metric labels or
traffic volumes are operationally sensitive. MCP traffic remains on FastMCP's
configured Streamable HTTP path.

## MCP Inspector

```bash
make inspect
# or with reload
make inspect-dev
```

For authenticated HTTP inspection, configure the inspector/client to send a
Bearer token with the scopes needed by the tools being tested.
