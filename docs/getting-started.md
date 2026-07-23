# Getting Started

This guide covers installing, configuring, and running the ModelArk Seed
Multimodal MCP Server.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (modern Python package manager)
- BytePlus account with Seed Audio, Seedream, and/or Seedance activated

## Installation

Clone the repository and install dependencies:

```bash
git clone <repo-url> modelark-mcp
cd modelark-mcp
cp .env.example .env
uv sync
```

## Configuration

Edit `.env` and fill in your BytePlus credentials:

```dotenv
BYTEPLUS_MODELARK_API_KEY=<your-modelark-key>
BYTEPLUS_SEED_AUDIO_API_KEY=<your-seed-audio-key>
```

ModelArk keys are region-scoped. Verify the base URL matches your region's
endpoint. The defaults point to the `ap-southeast` region.

If a credential is absent, the server skips registering that product's
tools. This means you can run with only Seedream enabled, for example.

## Running the Server

### stdio (default, for local MCP clients)

```bash
make start
# or
uv run python -m modelark_mcp
```

### Streamable HTTP (loopback development)

```bash
make start-http
# or
MCP_TRANSPORT=http MCP_PORT=3000 uv run python -m modelark_mcp
```

Non-loopback HTTP is fail-closed and requires JWT issuer, audience, JWKS,
Host, and Origin configuration. See [Transports](transports.md).

### Dev mode (with auto-reload)

```bash
make dev
```

## Verifying Your Setup

Run the Phase 0 verification script to confirm your credentials and model
IDs work:

```bash
uv run python scripts/verify_phase0.py
```

This performs minimal billable calls to each product (one image, one audio,
one Seedance task that is immediately cancelled) and prints redacted
responses.

## Using with MCP Clients

### Claude Desktop

Add the server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "modelark-seed": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/modelark-mcp", "python", "-m", "modelark_mcp"],
      "env": {
        "BYTEPLUS_MODELARK_API_KEY": "<your-key>",
        "BYTEPLUS_SEED_AUDIO_API_KEY": "<your-key>"
      }
    }
  }
}
```

### MCP Inspector

Launch the FastMCP inspector to explore tools interactively:

```bash
make inspect
```

## Next Steps

- [Configuration](configuration.md) — full environment variable reference
- [Tools](tools.md) — tool schemas and usage examples
- [Transports](transports.md) — stdio vs HTTP deployment
