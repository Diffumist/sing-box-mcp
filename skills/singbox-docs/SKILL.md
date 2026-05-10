---
name: singbox-docs
description: Use this skill when answering sing-box configuration, migration, TLS, DNS, inbound, outbound, route, rule, certificate, or option questions. It constrains the agent to query the sing-box-mcp server first, require a target sing-box version for content answers, and report official source/provenance instead of relying on model memory.
---

# sing-box Documentation Query Discipline

Use the `singbox_docs` MCP tool as the source of truth for sing-box documentation answers.

## Required Workflow

1. Identify whether the user is asking about sing-box configuration, behavior, fields, examples, migration, or version compatibility.
2. Confirm the target sing-box version before answering content questions.
   - If the user gave a version, use it exactly, for example `version="1.14.0"`.
   - If the user did not give a version, ask for it before giving a configuration answer.
   - Use `version="latest"` only for `stats`, `refresh`, or broad `list` discovery.
3. Query official docs with `singbox_docs` before answering.
   - Use `search` to find likely pages.
   - Use `info` for the authoritative page.
   - Use `examples` only when the user asks for a config example or when a snippet is needed.
4. Check field-level version notes in the MCP result.
   - Treat `Since sing-box X.Y.Z` as unavailable before that version.
   - Treat `Deprecated in sing-box X.Y.Z` as deprecated at or after that version.
   - Treat `Removed in sing-box X.Y.Z` as unavailable at or after that version.
   - Treat `Changes in sing-box X.Y.Z` as a warning to mention when it affects the answer.
5. Answer concisely with the relevant page path or URL.

## Answer Rules

- Do not answer sing-box field availability from memory.
- Do not invent fields that were not found in official docs.
- Do not omit the target version when discussing whether a field is valid.
- Prefer minimal config snippets and mark placeholders clearly.
- Include caveats for build tags, deprecated fields, removed fields, and provider-specific options.

## Useful Calls

```json
{"action": "search", "query": "cloudflare api token dns01", "version": "1.14.0"}
{"action": "info", "query": "configuration/shared/dns01_challenge", "version": "1.14.0"}
{"action": "info", "query": "configuration/shared/certificate-provider/acme", "version": "1.14.0"}
{"action": "examples", "query": "configuration/shared/tls", "version": "1.14.0"}
```
