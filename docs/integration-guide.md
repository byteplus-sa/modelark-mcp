# Integration Guide

How to connect the ModelArk Seed MCP server to popular MCP clients.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Python 3.12+
- BytePlus account with ModelArk API key and/or Seed Audio API key
- This repository cloned locally

## Server Overview

The server runs as a `stdio` process — the MCP client spawns it as a
subprocess and communicates over stdin/stdout. The entry point is
`python -m modelark_mcp`, which injects `truststore` for macOS TLS
certificate verification before starting the FastMCP server.

**Always use `python -m modelark_mcp`** (not `fastmcp run`) in client
configurations — this ensures `truststore` loads before any provider
API calls.

## Providing Credentials

Two options:

1. **`.env` file** at the repository root (recommended for local dev):
   ```bash
   cp .env.example .env
   # Edit .env and fill in your API keys
   ```

2. **Inline in the client config** (recommended for shared configs):
   Pass the keys in the `env` block of the client's MCP server configuration.

The `.env` approach is simplest because the server automatically loads it.
Inline env vars take precedence.

## Claude Desktop

Add the server to your `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "modelark-seed": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/modelark-mcp",
        "run",
        "python",
        "-m",
        "modelark_mcp"
      ],
      "env": {
        "BYTEPLUS_MODELARK_API_KEY": "your_ark_api_key"  # pragma: allowlist secret,
        "BYTEPLUS_SEED_AUDIO_API_KEY": "your_seed_audio_key"  # pragma: allowlist secret
      }
    }
  }
}
```

Replace `/path/to/modelark-mcp` with the absolute path to your repository.

Fully quit and restart Claude Desktop. The tools appear under the hammer
icon. If you use the `.env` file approach, you can omit the `env` block.

## Cursor IDE

Create `.cursor/mcp.json` in your project root (or
`~/.cursor/mcp.json` for global config):

```json
{
  "mcpServers": {
    "modelark-seed": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/modelark-mcp",
        "run",
        "python",
        "-m",
        "modelark_mcp"
      ],
      "env": {
        "BYTEPLUS_MODELARK_API_KEY": "your_ark_api_key"  # pragma: allowlist secret,
        "BYTEPLUS_SEED_AUDIO_API_KEY": "your_seed_audio_key"  # pragma: allowlist secret
      }
    }
  }
}
```

Alternatively, use `${env:VAR}` interpolation to reference shell
environment variables:

```json
{
  "mcpServers": {
    "modelark-seed": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/modelark-mcp",
        "run",
        "python",
        "-m",
        "modelark_mcp"
      ],
      "env": {
        "BYTEPLUS_MODELARK_API_KEY": "${env:BYTEPLUS_MODELARK_API_KEY}",
        "BYTEPLUS_SEED_AUDIO_API_KEY": "${env:BYTEPLUS_SEED_AUDIO_API_KEY}"
      }
    }
  }
}
```

Fully quit and restart Cursor. A green dot in Settings → Features → MCP
confirms the connection.

## VS Code (MCP Extension)

Create `.vscode/mcp.json` in your workspace root:

```json
{
  "servers": {
    "modelark-seed": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/modelark-mcp",
        "run",
        "python",
        "-m",
        "modelark_mcp"
      ],
      "envFile": "${workspaceFolder}/.env"
    },
    "inputs": []
  }
}
```

VS Code uses `"servers"` (not `"mcpServers"`). The `envFile` field loads
the repo's `.env` directly — no need to inline keys.

Run the **MCP: List Servers** command to verify the server is running.
Start/stop/restart controls appear as code lenses.

## MCP Inspector

The MCP Inspector provides a web UI for testing tools interactively.

**Option 1: Makefile (easiest)**

```bash
make inspect
```

This launches `fastmcp inspect src/modelark_mcp/server.py:mcp`. Note:
this path does not inject `truststore`, so it may fail on macOS for
ModelArk TLS. If you hit SSL errors, use option 2.

**Option 2: npx inspector (recommended for macOS)**

```bash
export BYTEPLUS_MODELARK_API_KEY=your_key  # pragma: allowlist secret
export BYTEPLUS_SEED_AUDIO_API_KEY=your_key  # pragma: allowlist secret

npx @modelcontextprotocol/inspector \
  uv --directory /path/to/modelark-mcp run python -m modelark_mcp
```

This injects `truststore` via the module entry point. The browser UI
opens — select **STDIO** transport and click **Connect**.

**Option 3: HTTP transport**

Start the server in HTTP mode:

```bash
make start-http
```

Then connect the Inspector to `http://127.0.0.1:3000/mcp`.

## Troubleshooting

### SSL Certificate Errors (macOS)

If you see `CERTIFICATE_VERIFY_FAILED`, the server wasn't started with
`truststore`. Always use `python -m modelark_mcp` (not `fastmcp run`)
in client configurations.

### "API key not configured" Error

The server skips registering tools for products without credentials. Check:

1. `.env` file exists at the repository root with the correct key names
2. Keys are spelled exactly: `BYTEPLUS_MODELARK_API_KEY`,
   `BYTEPLUS_SEED_AUDIO_API_KEY`
3. No leading/trailing whitespace in values
4. Run `make check-env` to validate

### Server Not Discovered by Client

1. Verify `uv` is on the client's PATH (or use a full path:
   `/Users/yourname/.local/bin/uv`)
2. Verify the `--directory` path is correct and absolute
3. Check the client's logs for stderr output from the server
4. Test manually: `uv --directory /path/to/modelark-mcp run python -m modelark_mcp`
   (should start and wait for stdin)

### Tools Missing

If only some products' tools are registered:

- No ModelArk key → no Seedream or Seedance tools (5 tools missing)
- No Seed Audio key → no Seed Audio tools (2 tools missing)

Both keys are required for all 9 tools to appear.

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `BYTEPLUS_MODELARK_API_KEY` | For image/video | — | ModelArk Bearer auth key |
| `BYTEPLUS_SEED_AUDIO_API_KEY` | For audio | — | Seed Speech X-Api-Key |
| `BYTEPLUS_MODELARK_BASE_URL` | No | `https://ark.ap-southeast.bytepluses.com/api/v3` | ModelArk region endpoint |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | No | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech endpoint |
| `SEEDREAM_DEFAULT_MODEL` | No | `dola-seedream-5-0-pro-260628` | Seedream model ID |
| `SEEDANCE_DEFAULT_MODEL` | No | `dreamina-seedance-2-0-260128` | Seedance model ID |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` or `http` |
| `MCP_HOST` | No | `127.0.0.1` | HTTP bind address |
| `MCP_PORT` | No | `3000` | HTTP port |
| `ARTIFACT_DIR` | No | `.artifacts` | Local artifact storage |
| `ARTIFACT_TTL_SECONDS` | No | `604800` (7 days) | Artifact retention |