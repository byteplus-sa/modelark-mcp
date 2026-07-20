---
name: fastmcp-docs
description: Research and answer questions using the official FastMCP documentation index bundled with this skill. Use this whenever the user asks about FastMCP, building an MCP server or client in Python, FastMCP tools/resources/prompts, the `FastMCP` class, MCP transports, MCP auth/OAuth, MCP middleware, FastMCP apps with interactive UIs, or installing/running FastMCP servers — even when they do not explicitly mention `llms.txt`. Also use this skill when the user asks to create or scaffold a FastMCP MCP server. Search the bundled `llms.txt`, then fetch only the relevant live documentation pages.
---

# FastMCP Docs

Use the bundled `llms.txt` as the discovery map for official FastMCP documentation. The index lists page titles and canonical URLs — it does not contain the evidence needed to answer detailed questions. Discover with the index, then read a small number of relevant live pages.

## What is FastMCP

FastMCP is the standard Python framework for building MCP (Model Context Protocol) applications. MCP is the open protocol that connects LLMs to tools and data; FastMCP makes it Pythonic — you declare a tool with a plain function and the schema, validation, and documentation are generated automatically.

FastMCP 1.0 was incorporated into the official MCP Python SDK in 2024. The actively maintained standalone project is made by the Prefect team and powers the majority of MCP servers across all languages. As of v3.0.0 (February 2026), the repository moved from `jlowin/fastmcp` to [`PrefectHQ/fastmcp`](https://github.com/PrefectHQ/fastmcp) under Prefect's stewardship; the current release is v3.4.4 (July 2026).

Three pillars:

- **Servers** — expose `tools`, `resources`, and `prompts` to LLMs via the `FastMCP` class.
- **Clients** — connect to any MCP server (local or remote, programmatic or CLI) with full protocol support.
- **Apps** — give tools interactive UIs rendered directly in the conversation.

A minimal server:

```python
from fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

## Source contract

- Treat `llms.txt` as the required discovery source. Use the copy beside this `SKILL.md` so the skill stays self-contained when installed elsewhere.
- Every indexed URL is a candidate, not proof of a technical claim.
- Verify substantive claims against the selected live `gofastmcp.com` pages.
- Prefer official FastMCP docs over blogs, search snippets, or third-party summaries.
- Context7 library `/prefecthq/fastmcp` can be used as corroboration when available; the canonical page URL from `llms.txt` remains the citation target.

## Find the index

The bundled `llms.txt` lives next to this `SKILL.md`:

```
llms.txt
```

Read it directly with the Read tool, or grep it for keywords. The skill loader resolves paths relative to this skill's base directory, so the filename alone is enough regardless of where the skill is installed (project `.agents/` or global `~/.agents/`).

## Research workflow

1. Identify the component, transport, auth pattern, or API in the request. Preserve exact names: `FastMCP`, `@mcp.tool`, `@mcp.resource`, `@mcp.prompt`, `mcp.run`, `Client`, transport names (`stdio`, `http`, `sse`), etc.
2. Search the index with two or three focused query variants:

   ```bash
   grep -i "middleware" llms.txt
   grep -i "oauth\|auth" llms.txt
   grep -i "composition\|compose" llms.txt
   ```

3. Select the smallest useful source set — normally one overview/guide plus one API reference page. Avoid collecting many loosely related pages.
4. Fetch and read those live official pages (append `.md` to any `gofastmcp.com` URL). For current SDK/API details, also query Context7 if available. If a page is unavailable, try the next indexed candidate rather than guessing.
5. Answer at the user's level: result first, then implementation details, limitations, and sources.
6. Cite each important factual claim with its canonical `gofastmcp.com` URL.

Match the requested depth. For a concise answer, target one short explanation, three to six actionable bullets, and two to five sources. Do not turn a link-finding request into a full tutorial unless asked.

## Creating a FastMCP MCP server

When the user asks to create, scaffold, or build a FastMCP server, reference the bundled `llms.txt` to ground the implementation in current docs, then:

1. Confirm the transport (default `stdio` for local/CLI; `http` for web services) and whether auth, middleware, resources, prompts, or apps are needed.
2. Start from the minimal server shape above and add only what is needed (YAGNI).
3. Use the decorator API (`@mcp.tool`, `@mcp.resource`, `@mcp.prompt`) — schema and validation are auto-generated from type hints and docstrings.
4. Guard entrypoint with `if __name__ == "__main__": mcp.run()` so MCP hosts can also launch it as a subprocess.
5. Verify against the relevant live docs pages (Server, Tools, Resources, Deployment/Running, and any optional feature like Auth, Middleware, Composition, Lifespan, Apps).

Relevant index sections for server building:

- Getting Started: Installation, Quickstart, Welcome
- Servers: Server, Tools, Resources & Templates, Prompts, Middleware, Composition, Lifespan, Context, Dependency Injection, Visibility, Testing
- Deployment: Running Your Server, HTTP Deployment, Server Configuration
- Auth (if needed): Authentication, Full OAuth Server, Remote OAuth, OAuth Proxy, OIDC Proxy, Token Verification, Multi Auth
- Apps (if interactive UIs are requested): Apps overview, Quickstart, Prefab, Generative, Custom HTML

## Evidence rules

- Clearly distinguish what the index shows (page title, section, URL) from what the live page states.
- Verify unstable details such as version numbers, transport defaults, CLI flags, env vars, and feature availability at answer time — this docs reflects the `main` branch and may include unreleased features (look for `New in version:` badges).
- For procedures, preserve prerequisites, transport constraints, auth requirements, and CLI-vs-code differences.
- For API answers, capture the class/method/decorator name, required parameters, return types, and documented errors only when the selected source supports them.

## Failure handling

- No matches: remove generic words, try synonyms (e.g., "auth" → "oauth", "compose" → "composition").
- Too many matches: narrow by adding the exact component or feature name.
- Live page unavailable: use another indexed page covering the same topic. Do not present the title alone as documentation content.
- Network unavailable: return the most relevant indexed links and state that their contents were not live-verified.

## Answer shape

Use only the sections the task needs:

```markdown
[Direct answer]

Implementation notes:
- [Actionable, source-backed detail]

Limitations or open points:
- [Only when relevant]

Sources:
- [Official page title](https://gofastmcp.com/...)
```

Keep sources close to the claims they support. A short factual question may need only one paragraph and one link.
