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

Use `python -m modelark_mcp` in client configurations so transport security
settings are applied consistently. The server module also injects `truststore`
before provider clients are created.

## Required Client Support

**Generation requires the MCP `2026-07-28` protocol and the FastMCP tasks
extension.** Tool discovery alone does not demonstrate task execution support.
A client must submit task-augmented calls and retrieve terminal output through
`tasks/get`; foreground calls to required-task tools are rejected before provider
submission. Status-only polls use `persist_output=false`; clients that advertise
tasks may automatically execute optional status tools as tasks too. Downloading
and persisting completed media requires a background task.

**Tested client:** the repository's locked FastMCP Python client **4.0.3**, with
its tasks extension, using in-process and subprocess stdio transports. Legacy
`Client(..., mode="legacy")` rejection is covered by protocol tests. These tests
mock providers and do not make billable generation calls.

**The Claude Desktop, Codex, Cursor, VS Code, and Inspector configuration examples
are connection templates; task execution on those clients has not been verified.**
Confirm protocol and extension support for your installed client version before
starting a generation workflow. See the [official FastMCP task documentation](https://gofastmcp.com/servers/tasks).

## Python Task Workflow

Run this from the repository using `uv run python`, with credentials configured
in `.env` and `SMOKE_REFERENCE_IMAGE_URL` pointing to an accessible reference
image. **This example submits one billable video generation.** The provider ID
is saved before polling; if polling fails, use that ID to resume retrieval rather
than repeating submission. The MCP task ID identifies the worker operation,
while the provider ID identifies the video generation.

```python
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp_tasks import call_tool_task


async def main():
    transport = StdioTransport(
        command=sys.executable, args=["-m", "modelark_mcp"]
    )
    async with Client(transport) as client:
        submission = await call_tool_task(
            client,
            "seedance_create_task",
            {"input": {
                "prompt": "A gentle camera move through the scene",
                "images": [{
                    "kind": "url",
                    "url": os.environ["SMOKE_REFERENCE_IMAGE_URL"],
                    "role": "reference_image",
                }],
                "duration": 5,
                "resolution": "480p",
            }},
        )
        print("MCP submission task:", submission.task_id)
        created = await submission.result()
        provider_id = created.structured_content["task_id"]
        directory = Path(".artifacts")
        directory.mkdir(exist_ok=True)
        with (directory / "provider_tasks.jsonl").open("a") as stream:
            stream.write(json.dumps({"task_id": provider_id}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

        for _ in range(30):
            status = await client.call_tool(
                "seedance_get_task",
                {"input": {"task_id": provider_id, "persist_output": False}},
            )
            state = status.structured_content["status"]
            if state == "succeeded":
                break
            if state in {"failed", "cancelled", "expired"}:
                raise RuntimeError(f"Provider task {provider_id}: {state}")
            await asyncio.sleep(10)
        else:
            raise TimeoutError(f"Resume polling provider task {provider_id}")

        persistence = await call_tool_task(
            client,
            "seedance_get_task",
            {"input": {"task_id": provider_id, "persist_output": True}},
        )
        completed = await persistence.result()
        print(completed.structured_content["video"])


asyncio.run(main())
```

`task.result()` waits through `tasks/get` and returns the terminal tool result.
In this single-process stdio example, FastMCP 4.0.3 automatically task-augments
`client.call_tool()` for the optional status tool as well; `persist_output=false`
still prevents downloads. The standalone smoke scripts use modern and public
`mode="legacy"` clients connected to the same in-process server lifespan to
exercise a genuinely foreground status call. Do not launch a second stdio server
against the same SQLite state to obtain that behavior.
A provider success can still have `video=null` when best-effort persistence
fails; inspect the result before treating the artifact as delivered. The same
submit/status/persistence sequence is tested offline by the smoke-workflow tests;
`tests/e2e/test_stdio_tasks.py` separately verifies a real subprocess task result.

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
        "BYTEPLUS_SEED_SPEECH_API_KEY": "your_seed_speech_key"  # pragma: allowlist secret
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
        "BYTEPLUS_SEED_SPEECH_API_KEY": "your_seed_speech_key"  # pragma: allowlist secret
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
        "BYTEPLUS_SEED_SPEECH_API_KEY": "${env:BYTEPLUS_SEED_SPEECH_API_KEY}"
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

This launches `fastmcp inspect src/modelark_mcp/server.py:mcp`; the server
module injects `truststore` before provider clients are created.

**Option 2: npx inspector (recommended for macOS)**

```bash
export BYTEPLUS_MODELARK_API_KEY=your_key  # pragma: allowlist secret
export BYTEPLUS_SEED_SPEECH_API_KEY=your_key  # pragma: allowlist secret

npx @modelcontextprotocol/inspector \
  uv --directory /path/to/modelark-mcp run python -m modelark_mcp
```

The browser UI opens—select **STDIO** transport and click **Connect**.

**Option 3: HTTP transport**

Start the server in HTTP mode:

```bash
make start-http
```

Then connect the Inspector to `http://127.0.0.1:3000/mcp`.

## Troubleshooting

### SSL Certificate Errors (macOS)

If you see `CERTIFICATE_VERIFY_FAILED`, confirm `truststore` is installed and
start through `python -m modelark_mcp` so the complete entrypoint runs.

### "API key not configured" Error

The server skips registering tools for products without credentials. Check:

1. `.env` file exists at the repository root with the correct key names
2. Keys are spelled exactly: `BYTEPLUS_MODELARK_API_KEY`,
   `BYTEPLUS_SEED_SPEECH_API_KEY`
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
| `BYTEPLUS_SEED_SPEECH_API_KEY` | For audio | — | Seed Speech X-Api-Key |
| `BYTEPLUS_MODELARK_BASE_URL` | No | `https://ark.ap-southeast.bytepluses.com/api/v3` | ModelArk region endpoint |
| `BYTEPLUS_SEED_AUDIO_BASE_URL` | No | `https://voice.ap-southeast-1.bytepluses.com` | Seed Speech endpoint |
| `SEEDREAM_DEFAULT_MODEL` | No | `dola-seedream-5-0-pro-260628` | Seedream model ID |
| `SEEDANCE_DEFAULT_MODEL` | No | `dreamina-seedance-2-0-260128` | Seedance model ID |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` or `http` |
| `MCP_HOST` | No | `127.0.0.1` | HTTP bind address |
| `MCP_PORT` | No | `3000` | HTTP port |
| `MCP_AUTH_MODE` | No | `local` | Set `jwt` for non-loopback HTTP |
| `MCP_JWT_JWKS_URI` | For JWT | — | HTTPS JSON Web Key Set URL |
| `MCP_JWT_ISSUER` | For JWT | — | Required token issuer |
| `MCP_JWT_AUDIENCE` | For JWT | — | Required token audience |
| `MCP_TENANT_CLAIM` | No | `tenant_id` | Tenant-isolation claim |
| `MCP_ALLOWED_HOSTS` | For HTTP | loopback | Accepted Host headers |
| `MCP_ALLOWED_ORIGINS` | For browser HTTP | — | Accepted browser origins |
| `ARTIFACT_DIR` | No | `.artifacts` | Local artifact storage |
| `ARTIFACT_TTL_SECONDS` | No | `604800` (7 days) | Artifact retention |

See [Configuration](configuration.md) for model bindings, body limits,
concurrency, and budget settings.
