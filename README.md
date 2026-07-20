# ModelArk Seed Multimodal MCP Server

A TypeScript [Model Context Protocol](https://modelcontextprotocol.io) server
that exposes BytePlus multimodal generation through a small, typed, safe tool
surface.

## Capabilities

- **Seed Audio** — full-scene audio generation through Seed Speech.
- **Seedream** — image generation and editing through ModelArk.
- **Seedance** — asynchronous video generation and task management through
  ModelArk.
- **Durable artifacts** — generated media is persisted locally so MCP resources
  remain usable after the provider URLs expire (2h for audio, 24h for
  image/video).
- **Transports** — local `stdio` by default, with protected Streamable HTTP for
  remote deployment.

Seedance and Seedream use the ModelArk data-plane host with Bearer
authentication. Seed Audio uses the Seed Speech host with `X-Api-Key`. The
server normalizes both behind one domain layer.

## Status

In planning. See [`plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md`](plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md)
for the full design, verified API inventory, tool contracts, and implementation
phases.

## Documentation

- [`plans/`](plans/) — implementation plans for features.
- [`specs/`](specs/) — future-looking specs and design docs.
- [`docs/`](docs/) — project documentation (install, configure, deploy).

See [`AGENTS.md`](AGENTS.md) for the documentation standard that governs these
directories.
