# Architecture Notes

These notes capture the implementation ideas taken from `mcp-nixos` and adapted
for a sing-box documentation MCP server.

## Core Idea

`mcp-nixos` works because it does not ask the model to remember a fast-moving
technical domain. It exposes MCP tools that query current, structured sources and
return model-friendly plain text.

For sing-box, the equivalent is:

```text
AI client
  -> singbox_docs MCP tool
  -> validate action/query/section/version
  -> search local documentation index or fetch official docs
  -> format concise plain text with source provenance
```

## Why A Local Index

sing-box documentation is mostly static documentation, not a live package index.
That makes a local docs index a good default:

- Faster than fetching pages per request.
- Search can include page title, path, headings, option names, and code blocks.
- Results can carry upstream provenance such as version, branch, commit, or
  fetch timestamp.
- Tests can use small fixture indexes.

Live fetching should exist as a refresh operation, not the default request path.

## Suggested Data Model

Each indexed page can be represented as:

```text
DocumentPage
  path: configuration/outbound/hysteria2
  title: Hysteria2
  lang: en
  section: outbound
  headings: [...]
  body_text: ...
  fields: [...]
  examples: [...]
  source_url: https://sing-box.sagernet.org/...
  upstream_ref: commit/tag/branch
```

The index should support:

- exact path lookup for `info`
- keyword search for `search`
- section browsing for `list`
- code block extraction for `examples`

## Tool Routing

Follow the `mcp-nixos` pattern:

1. Validate arguments at the MCP boundary.
2. Normalize aliases early.
3. Dispatch by `action`.
4. Keep source-specific logic out of `server.py`.
5. Return helpful plain text errors with example calls.

## Documentation Sections

Expected high-value sections:

- `configuration`
- `inbound`
- `outbound`
- `dns`
- `route`
- `rule`
- `rule-action`
- `experimental`
- `shared`
- `installation`
- `migration`

## Version Awareness

sing-box changes configuration fields over time. The MCP server should expose
provenance clearly:

- index version or upstream tag
- source commit if built from GitHub
- fetch timestamp if built from the live documentation site

Later, a versioned index could support queries like:

```json
{"action": "info", "query": "outbound/hysteria2", "version": "1.13"}
```

## Formatting Rules

Normal responses should be plain text:

```text
Page: Outbound / Hysteria2
Source: configuration/outbound/hysteria2
Upstream: v1.13.x

Fields:
* type: must be "hysteria2"
* server: server address
* server_port: server port

Examples:
...
```

Avoid returning raw parser internals or whole HTML documents.

## Minimal First Milestone

1. Create a static fixture index with several representative pages.
2. Implement `search`, `info`, `list`, and `stats`.
3. Add tests for routing and formatting.
4. Add an index builder that reads upstream markdown or MkDocs navigation.
5. Add `examples` extraction.
6. Add `refresh`.
