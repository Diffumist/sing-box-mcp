# AGENTS.md

## Project Overview

singbox-mcp is a planned Model Context Protocol server for sing-box
documentation. It should help AI assistants answer sing-box configuration
questions from official documentation instead of relying on stale model memory.

## Design Principles Borrowed From mcp-nixos

- Expose a small tool surface. Prefer one unified documentation tool over many
  narrow tools.
- Keep routing explicit: validate `action`, `section`, `version`, and `limit`
  before dispatching to source modules.
- Split implementation by responsibility:
  - `server.py` for MCP tool definitions and routing.
  - `config.py` for upstream URLs, limits, and defaults.
  - `index.py` or `caches.py` for documentation index loading.
  - `sources/` for upstream document fetchers and parsers.
  - `utils.py` for text cleanup, markdown parsing, and formatting helpers.
- Return plain text optimized for LLM consumption.
- Avoid raw HTML/JSON leakage in normal responses.
- Include helpful error messages with examples of valid calls.
- Track provenance: every index should know the upstream version, branch, commit,
  or fetch time it came from.
- Prefer official sources and deterministic local indexes over ad hoc web search.
- Use async MCP tools, but move blocking network or filesystem work into worker
  threads when needed.

## Proposed Structure

```text
singbox_mcp/
  server.py
  config.py
  index.py
  utils.py
  sources/
    official_docs.py
    github.py
tests/
docs/
  architecture.md
```

## Initial MCP Tool

Expose one tool first:

```text
singbox_docs(action, query="", section="", version="latest", lang="en", limit=20)
```

Supported actions:

- `search`: keyword search across titles, paths, headings, body text, and field
  names.
- `info`: return one documentation page or configuration object.
- `list`: list known pages or objects under a section.
- `examples`: return official configuration examples related to a query.
- `stats`: show index size and provenance.
- `refresh`: rebuild the local docs index.

## Coding Conventions

- Python 3.11+.
- Keep line length reasonable, target 120 columns.
- Prefer structured parsing over regex-only scraping when possible.
- Keep tests focused on routing, parsing, formatting, and index behavior.
- Do not suppress lint or type checker warnings with ignore comments; fix the
  underlying issue.

## Response Style

All MCP responses should be concise plain text:

- Start with the direct result.
- Include the source page path or URL.
- Include version/provenance when relevant.
- Include examples only when requested or essential.
- For missing results, suggest valid nearby sections or example calls.
