# sing-box-mcp

`sing-box-mcp` is a FastMCP server for querying official sing-box documentation.
It builds a local index from `https://sing-box.sagernet.org/` and returns concise
plain text with source paths and version-aware field notes.

## Tool

```text
singbox_docs(action, query="", section="", version="latest", lang="en", limit=20)
```

Actions:

- `search`: search official docs.
- `info`: return one page or configuration object.
- `list`: list pages under a section.
- `examples`: return official code blocks.
- `stats`: show local index and provenance.
- `refresh`: rebuild the local index from the official sitemap.

For content queries, pass an explicit target sing-box version:

```json
{"action": "info", "query": "configuration/shared/tls", "version": "1.14.0"}
```

The server checks documentation notes such as `Since sing-box 1.14.0`,
`Changes in sing-box 1.13.0`, `Deprecated in sing-box 1.11.0`, and
`Removed in sing-box 1.14.0`.

## Run With uvx

After publishing to PyPI:

```bash
uvx sing-box-mcp
```

MCP client config:

```json
{
  "mcpServers": {
    "sing-box-mcp": {
      "command": "uvx",
      "args": ["sing-box-mcp"]
    }
  }
}
```

For local testing before publishing:

```bash
uvx --from . sing-box-mcp
```

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/mypy singbox_mcp
```

Build release artifacts:

```bash
.venv/bin/python -m build
.venv/bin/twine check dist/*
```

Publish:

```bash
.venv/bin/twine upload dist/*
```

## Agent Skill

A lightweight Codex-style skill is included at
`skills/singbox-docs/SKILL.md`. It constrains agents to confirm the target
sing-box version, query this MCP server first, check version notes, and cite
official source pages.
