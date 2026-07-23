# Deployment

Remote deployment uses FastMCP Streamable HTTP with fail-closed JWT
authentication. Local stdio remains the simplest operating mode.

## Build the container

```bash
docker build --tag modelark-mcp:latest .
```

The image uses pinned Python and uv versions, installs the locked production
environment, runs as UID/GID 1001, and probes `/health` with Python's standard
library. The image intentionally defaults to JWT mode; verifier settings must
be supplied at runtime.

## Run one protected instance

```bash
docker run --detach \
  --name modelark-mcp \
  --publish 127.0.0.1:3000:3000 \
  --env BYTEPLUS_MODELARK_API_KEY \
  --env BYTEPLUS_SEED_AUDIO_API_KEY \
  --env MCP_JWT_JWKS_URI=https://id.example.com/.well-known/jwks.json \
  --env MCP_JWT_ISSUER=https://id.example.com/ \
  --env MCP_JWT_AUDIENCE=modelark-mcp \
  --env MCP_ALLOWED_HOSTS=mcp.example.com,127.0.0.1 \
  --env MCP_ALLOWED_ORIGINS=https://client.example.com \
  --volume modelark-artifacts:/app/.artifacts \
  modelark-mcp:latest
```

Place a TLS-terminating reverse proxy in front of the loopback-published port.
Disable proxy buffering for Streamable HTTP/SSE and set read/send timeouts at
least as high as `BYTEPLUS_REQUEST_TIMEOUT_MS`. Preserve the public Host header
so the server allowlist can validate it.

## Probes and monitoring

```bash
curl --fail http://127.0.0.1:3000/health
curl --fail http://127.0.0.1:3000/ready
curl --fail http://127.0.0.1:3000/metrics
```

- `/health` reports process liveness without contacting providers.
- `/ready` checks the runtime-owned SQLite state and artifact directory.
- `/metrics` exports tool/provider request counts, duration, retries, artifact
  writes, and budget rejections for Prometheus.

Provider calls also create FastMCP/OpenTelemetry child spans when tracing is
configured. Application logs are structured JSON on stderr and redact secrets.

## Kubernetes shape

Use one replica with a persistent volume until distributed state adapters are
implemented. The important container settings are:

```yaml
containers:
  - name: modelark-mcp
    image: modelark-mcp:latest
    ports:
      - name: http
        containerPort: 3000
    env:
      - {name: MCP_TRANSPORT, value: http}
      - {name: MCP_HOST, value: 0.0.0.0}
      - {name: MCP_AUTH_MODE, value: jwt}
      - {name: MCP_JWT_JWKS_URI, value: "https://id.example.com/.well-known/jwks.json"}
      - {name: MCP_JWT_ISSUER, value: "https://id.example.com/"}
      - {name: MCP_JWT_AUDIENCE, value: modelark-mcp}
      - {name: MCP_ALLOWED_HOSTS, value: mcp.example.com}
      - {name: MCP_ALLOWED_ORIGINS, value: "https://client.example.com"}
    readinessProbe:
      httpGet: {path: /ready, port: http}
    livenessProbe:
      httpGet: {path: /health, port: http}
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      runAsNonRoot: true
      runAsUser: 1001
    volumeMounts:
      - {name: artifacts, mountPath: /app/.artifacts}
```

Mount `/app/.artifacts` writable even with a read-only root filesystem. Load
provider credentials from a Secret rather than literal manifest values.

## Security checklist

- Use HTTPS and JWT mode for every non-loopback bind.
- Pin issuer, audience, and JWKS URI; issue least-privilege tool scopes.
- Set explicit Host and Origin allowlists.
- Keep the HTTP body limit and provider URL SSRF checks enabled.
- Mount the artifact directory with least privilege and protect backups.
- Restrict operational endpoints at the proxy/network layer as appropriate.
- Run one replica; filesystem/SQLite state and in-process limiters are not a
  distributed coordination mechanism.
- Keep `uv.lock`, base images, and GitHub Actions pins current through review.

See [Configuration](configuration.md), [Transports](transports.md), and
[Troubleshooting](troubleshooting.md) for the complete operating contract.
