"""MCP entry point and tool routing for sing-box-mcp."""

from __future__ import annotations

import asyncio
from types import ModuleType
from typing import Any

from .config import DEFAULT_LANG, DEFAULT_LIMIT, DEFAULT_VERSION, MAX_LIMIT, SUPPORTED_LANGS
from .index import DocumentPage, DocsIndex, load_cached_index, load_or_refresh_index, refresh_index, save_cached_index
from .utils import clamp_limit, format_bullets, summarize_text
from .versioning import availability_status, is_explicit_version

fastmcp_module: ModuleType | None
try:
    import fastmcp as imported_fastmcp
except ImportError:  # pragma: no cover - exercised only when runtime dependency is missing.
    fastmcp_module = None
else:
    fastmcp_module = imported_fastmcp

VALID_ACTIONS = {"search", "info", "list", "examples", "stats", "refresh"}

TOOL_INSTRUCTIONS = """Query official sing-box documentation.

Use search for discovery, info for one page, list for sections, examples for
official code blocks, stats for provenance, and refresh to rebuild the local
index from https://sing-box.sagernet.org/.

For search, info, and examples, pass the target sing-box version explicitly,
for example version="1.14.0", so field availability can be checked.
"""


def handle_singbox_docs(
    action: str,
    query: str = "",
    section: str = "",
    version: str = DEFAULT_VERSION,
    lang: str = DEFAULT_LANG,
    limit: int = DEFAULT_LIMIT,
    *,
    docs_index: DocsIndex | None = None,
) -> str:
    """Validate and route a singbox_docs call."""

    normalized_action = action.strip().lower()
    normalized_lang = lang.strip().lower()
    normalized_version = version.strip().lower()
    result_limit = clamp_limit(limit)

    validation_error = validate_args(normalized_action, normalized_lang, normalized_version, limit)
    if validation_error:
        return validation_error

    if normalized_action == "refresh":
        index = refresh_index(lang=normalized_lang, version=DEFAULT_VERSION)
        save_cached_index(index)
        return format_stats(index, prefix="Refreshed index")

    if docs_index is None:
        if normalized_action == "stats":
            cached = load_cached_index(lang=normalized_lang, version=DEFAULT_VERSION)
            if cached is None:
                return missing_index_message(normalized_lang)
            docs_index = cached
        else:
            docs_index = load_or_refresh_index(lang=normalized_lang, version=DEFAULT_VERSION)

    if normalized_action == "stats":
        return format_stats(docs_index)
    if normalized_action == "search":
        return route_search(docs_index, query=query, section=section, version=normalized_version, limit=result_limit)
    if normalized_action == "info":
        return route_info(docs_index, query=query, version=normalized_version)
    if normalized_action == "list":
        return route_list(docs_index, section=section, limit=result_limit)
    if normalized_action == "examples":
        return route_examples(docs_index, query=query, section=section, version=normalized_version, limit=result_limit)

    return valid_actions_message()


def validate_args(action: str, lang: str, version: str, limit: int) -> str:
    if action not in VALID_ACTIONS:
        return valid_actions_message()
    if lang not in SUPPORTED_LANGS:
        return "Invalid lang. Use one of: en, zh.\nExample: singbox_docs(action=\"search\", query=\"dns\", lang=\"en\")"
    if version != DEFAULT_VERSION and not is_explicit_version(version):
        return 'Invalid version. Use "latest" for index operations or an explicit sing-box version like "1.14.0".'
    if action in {"search", "info", "examples"} and version == DEFAULT_VERSION:
        return (
            "Missing target sing-box version.\n"
            "Because official docs mark fields with notes such as \"Since sing-box 1.14.0\", "
            "\"Changes in sing-box 1.13.0\", \"Deprecated in sing-box 1.11.0\", and "
            "\"Removed in sing-box 1.14.0\", pass an explicit version first.\n"
            'Example: singbox_docs(action="info", query="configuration/outbound/hysteria2", version="1.14.0")'
        )
    if limit < 1 or limit > MAX_LIMIT:
        return f"Invalid limit. Use an integer from 1 to {MAX_LIMIT}."
    return ""


def valid_actions_message() -> str:
    return (
        "Invalid action. Use one of: search, info, list, examples, stats, refresh.\n"
        "Examples:\n"
        '- singbox_docs(action="search", query="hysteria2 outbound")\n'
        '- singbox_docs(action="info", query="configuration/outbound/hysteria2")\n'
        '- singbox_docs(action="list", section="outbound")'
    )


def missing_index_message(lang: str) -> str:
    return (
        f"No local sing-box documentation index found for lang={lang}.\n"
        'Build it with: singbox_docs(action="refresh")\n'
        'Or query directly with: singbox_docs(action="search", query="dns")'
    )


def route_search(index: DocsIndex, *, query: str, section: str, version: str, limit: int) -> str:
    if not query.strip():
        return 'Missing query. Example: singbox_docs(action="search", query="hysteria2 outbound")'
    results = index.search(query=query, section=section, limit=limit)
    if not results:
        sections = ", ".join(index.sections()[:12])
        return (
            f'No results for "{query}".\n'
            f"Known sections: {sections}\n"
            'Example: singbox_docs(action="list", section="outbound")'
        )
    lines = [f'Results for "{query}" ({len(results)} shown)', f"Target sing-box version: {version}", provenance_line(index)]
    for number, (score, page) in enumerate(results, start=1):
        headings = ", ".join(page.headings[:5])
        lines.append(f"{number}. {page.title}")
        lines.append(f"   Path: {page.path}")
        lines.append(f"   Source: {page.source_url}")
        lines.append(f"   Score: {score}")
        if headings:
            lines.append(f"   Headings: {headings}")
    return "\n".join(lines)


def route_info(index: DocsIndex, *, query: str, version: str) -> str:
    if not query.strip():
        return 'Missing query. Example: singbox_docs(action="info", query="configuration/outbound/hysteria2")'
    page = index.find_page(query)
    if page is None:
        nearby = index.search(query=query, limit=5)
        lines = [f'No exact page found for "{query}".']
        if nearby:
            lines.append("Nearby pages:")
            for _, candidate in nearby:
                lines.append(f"- {candidate.path}: {candidate.title}")
        lines.append('Example: singbox_docs(action="search", query="hysteria2")')
        return "\n".join(lines)
    return format_page_info(index, page, target_version=version)


def route_list(index: DocsIndex, *, section: str, limit: int) -> str:
    pages = index.list_pages(section=section)
    if not pages:
        sections = ", ".join(index.sections())
        return (
            f'No pages found under section "{section}".\n'
            f"Known sections: {sections}\n"
            'Example: singbox_docs(action="list", section="outbound")'
        )
    title = f'Pages under "{section}"' if section else "Known pages"
    lines = [f"{title} ({min(len(pages), limit)} of {len(pages)} shown)", provenance_line(index)]
    for page in pages[:limit]:
        lines.append(f"- {page.path}: {page.title}")
    return "\n".join(lines)


def route_examples(index: DocsIndex, *, query: str, section: str, version: str, limit: int) -> str:
    if not query.strip():
        return 'Missing query. Example: singbox_docs(action="examples", query="hysteria2 outbound")'
    results = index.search(query=query, section=section, limit=limit)
    pages = [page for _, page in results if page.examples]
    if not pages:
        return (
            f'No official examples found for "{query}".\n'
            'Try: singbox_docs(action="info", query="configuration/outbound/hysteria2")'
        )
    lines = [f'Official examples for "{query}"', f"Target sing-box version: {version}", provenance_line(index)]
    shown = 0
    for page in pages:
        for example in page.examples:
            shown += 1
            lines.append("")
            lines.append(f"Example {shown}: {page.title}")
            lines.append(f"Path: {page.path}")
            lines.append(f"Source: {page.source_url}")
            lines.append("```")
            lines.append(summarize_text(example, max_chars=2200))
            lines.append("```")
            if shown >= limit:
                return "\n".join(lines)
    return "\n".join(lines)


def format_page_info(index: DocsIndex, page: DocumentPage, *, target_version: str) -> str:
    lines = [
        f"Page: {page.title}",
        f"Path: {page.path}",
        f"Source: {page.source_url}",
        f"Last modified: {page.lastmod or 'unknown'}",
        f"Target sing-box version: {target_version}",
        provenance_line(index),
        "",
        "Headings:",
        format_bullets(page.headings, limit=20),
    ]
    if page.fields:
        lines.extend(["", "Fields:", format_fields(page, target_version=target_version, limit=30)])
    lines.extend(["", "Content:", summarize_text(page.body_text, max_chars=2400)])
    return "\n".join(lines)


def format_fields(page: DocumentPage, *, target_version: str, limit: int) -> str:
    lines: list[str] = []
    for field_name in page.fields[:limit]:
        notes = page.field_availability.get(field_name, [])
        status = availability_status(notes, target_version)
        if notes:
            note_text = "; ".join(note.note for note in notes)
            lines.append(f"- {field_name}: {status}; {note_text}")
        else:
            lines.append(f"- {field_name}: {status}")
    return "\n".join(lines) if lines else "- none"


def format_stats(index: DocsIndex, prefix: str = "Index") -> str:
    sections = ", ".join(f"{section}={count_pages(index, section)}" for section in index.sections())
    return "\n".join(
        [
            f"{prefix}: {len(index.pages)} pages",
            f"Language: {index.lang}",
            f"Version: {index.version}",
            f"Source: {index.source}",
            f"Fetched at: {index.fetched_at}",
            f"Sections: {sections}",
        ]
    )


def count_pages(index: DocsIndex, section: str) -> int:
    return sum(1 for page in index.pages if page.section == section)


def provenance_line(index: DocsIndex) -> str:
    return f"Provenance: {index.source}, fetched {index.fetched_at}, version {index.version}, lang {index.lang}"


def create_mcp() -> Any | None:
    if fastmcp_module is None:
        return None

    fastmcp_class = getattr(fastmcp_module, "FastMCP")
    mcp = fastmcp_class(name="sing-box-mcp", instructions=TOOL_INSTRUCTIONS, version="0.1.0")

    @mcp.tool
    async def singbox_docs(
        action: str,
        query: str = "",
        section: str = "",
        version: str = DEFAULT_VERSION,
        lang: str = DEFAULT_LANG,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        """Query official sing-box documentation from a local index."""

        return await asyncio.to_thread(
            handle_singbox_docs,
            action,
            query,
            section,
            version,
            lang,
            limit,
        )

    return mcp


mcp = create_mcp()


def main() -> None:
    """Run the sing-box-mcp server."""

    if mcp is None:
        raise SystemExit("fastmcp is not installed. Install project dependencies before running sing-box-mcp.")
    mcp.run()
