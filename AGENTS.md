# AGENTS.md

## Project

ModelArk Seed Multimodal MCP Server — a Python MCP server (FastMCP on uv)
that exposes BytePlus multimodal generation through a small, typed, safe tool
surface:

- **Seed Audio** — full-scene audio generation through Seed Speech.
- **Seedream** — image generation and editing through ModelArk.
- **Seedance** — asynchronous video generation and task management through
  ModelArk.
- **Durable artifacts** — MCP resources for generated media whose provider URLs
  expire (2h for audio, 24h for image/video).
- **Transports** — local `stdio` first, with protected Streamable HTTP as a
  deployable option (both natively supported by FastMCP).

Seedance and Seedream share the ModelArk data-plane host and Bearer
authentication, while Seed Audio is hosted by Seed Speech and uses `X-Api-Key`.
The server uses two provider gateways behind one normalized domain layer. See
`plans/PLAN_MODELARK_SEED_MULTIMODAL_MCP.md` for the full design.

## Repository Layout

```text
modelark-mcp/
├── AGENTS.md          # project conventions for agents (this file)
├── CLAUDE.md          # redirects to AGENTS.md
├── README.md          # project overview and quickstart
├── Makefile           # task runner (wraps uv + fastmcp CLI)
├── pyproject.toml     # project metadata and dependencies (uv)
├── uv.lock            # locked dependencies for reproducible installs
├── fastmcp.json       # declarative FastMCP server configuration
├── .agents/skills/    # canonical project skills (source of truth)
├── .claude/skills/    # per-skill symlinks mirroring .agents/skills/
├── plans/             # implementation plans for features
├── specs/             # future-looking specs and design docs
├── docs/              # project documentation
├── src/modelark_mcp/  # server source (Python package)
└── tests/             # tests (pytest)
```

## Skills and Agent Configuration

Agent skills and the agent rule files must stay aligned across the tools
that read this repository:

- **`.agents/skills/` is the canonical source of truth** for project
  skills. Add and edit skills here. `skills-lock.json` pins externally
  sourced skills (e.g. `mcp-builder` from `anthropics/skills`); locally
  authored skills (`fastmcp`, `fastmcp-docs`) are committed directly.
- **`.claude/skills/` mirrors `.agents/skills/`** through one relative
  symlink per skill (e.g. `.claude/skills/mcp-builder` →
  `../../.agents/skills/mcp-builder`). When you add a skill under
  `.agents/skills/<name>/`, also create the matching
  `.claude/skills/<name>` symlink so Claude Code discovers the same skill.
  Never edit files through the `.claude/skills/` symlinks — change
  `.agents/skills/` and both trees update.
- **Keep project skills current with the MCP server.** When a code change
  adds, removes, renames, or materially changes MCP tools, resources,
  configuration, auth scopes, transport behavior, or output schemas, update
  the affected skill docs in `.agents/skills/` in the same unit of work.
  Treat agent-facing skills as shipped documentation for the current server,
  not as optional follow-up polish.
- **`CLAUDE.md` imports `AGENTS.md`.** `CLAUDE.md` contains a single
  `@AGENTS.md` import so Claude Code loads the same rules. Edit `AGENTS.md`
  only; never duplicate content into `CLAUDE.md`, so the two stay in sync.

## Documentation Standard

All non-code documentation lives in one of three top-level directories. Keep
their purposes distinct and do not mix them.

### `plans/` — Plans for features

Concrete, actionable implementation plans for a specific feature or unit of
work. A plan describes **how** to build something, with enough detail (code
structures, API signatures, data models, file organization, phases) that an
engineer or agent can execute it without re-deriving the design.

- Naming convention: `PLAN_<FEATURE_OR_SCOPE>.md`.
- Include frontmatter (`title`, `type: plan`, `status`, `created`, `updated`,
  `tags`, `source`, `related`) when the plan draws on external research.
- A plan is a living document: update `status` and `updated` as work
  progresses. Once shipped, the durable decisions should move to `specs/` or
  `docs/` and the plan can be archived or marked `status: shipped`.
- Reference the plan by path when writing code that implements it.

### `specs/` — Future-looking specs and design docs

Specifications describing what the system **is or will be**, independent of any
single implementation effort. Specs are the source of truth for contracts,
interfaces, and intended behavior. A spec may describe current reality ("what
it is today") or a future state ("what it will become"); label the horizon
explicitly when it matters.

- Naming convention: `SPEC_<DOMAIN_OR_CAPABILITY>.md`, or a short descriptive
  filename for cross-cutting specs (e.g. `security.md`, `error-model.md`).
- Include frontmatter with `status: draft | proposed | accepted | deprecated`
  and a `horizon: current | future` field when the spec is forward-looking.
- Specs hold: API contracts, tool schemas, data models, security models, error
  taxonomies, capability registries, and architecture decisions that outlive a
  single plan.
- Prefer updating an existing spec over creating a new one. When a spec is
  superseded, mark it `deprecated` and point to the successor rather than
  deleting it.

### `docs/` — Project documentation

User- and contributor-facing documentation for the project as it exists today.
This is the published handbook: how to install, configure, run, deploy, and
troubleshoot the server.

- Examples: `getting-started.md`, `configuration.md`, `transports.md`,
  `tools.md`, `deployment.md`, `troubleshooting.md`.
- Documentation describes **current** behavior. When something is planned but
  not yet built, link to the relevant entry in `plans/` or `specs/` instead of
  documenting it as if it already works.
- Keep docs in sync with the shipped code. If the code and docs disagree, the
  code is correct until the docs are updated; open a follow-up if they cannot
  be reconciled immediately.

## Working Conventions

- **Read before writing.** Before implementing, read the relevant plan in
  `plans/`, the applicable specs in `specs/`, and any existing docs in `docs/`.
- **Plans reference specs.** A plan may quote or link to a spec, but the spec
  remains the long-lived source of truth. Do not duplicate a contract into a
  plan and then let the two drift; link instead.
- **Docs reflect shipped work.** Do not document a feature in `docs/` until it
  is built. Use `plans/` and `specs/` for not-yet-shipped work.
- **Keep docs and skills in lockstep with shipped MCP changes.** If a server
  change affects tool inventory, resources, schemas, env vars, or user-facing
  workflows, update the relevant files in `docs/`, `README.md`, and
  `.agents/skills/` before considering the work complete. If full reconciliation
  is too large for the current task, document the remaining drift explicitly.
- **Frontmatter.** Plans and specs use YAML frontmatter. Docs may use
  frontmatter for title and weight/order but are not required to.
- **Diagrams.** Use Mermaid for architecture, sequence, and flow diagrams. Keep
  diagrams in the relevant plan or spec and update them when the design
  changes.
- **Sources.** When a plan or spec draws on external documentation, record the
  URLs in a `source:` frontmatter field or a `## Sources` section with access
  dates. Prefer official BytePlus and Model Context Protocol sources.
- **Secrets.** Never commit credentials, API keys, or provider response
  fixtures containing real media. Redact before saving examples.
