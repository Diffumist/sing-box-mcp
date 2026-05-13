"""Documentation index loading, refreshing, and querying."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

from .config import INDEX_CACHE_DIR, REFRESH_PAGE_LIMIT, REQUEST_TIMEOUT_SECONDS, SITEMAP_URL, USER_AGENT
from .utils import extract_article, normalize_doc_path, path_to_section, tokenize
from .versioning import AvailabilityNote

QUERY_ALIASES = {
    "doh": ["dns", "https"],
    "dot": ["dns", "tls"],
    "doq": ["dns", "quic"],
    "hy2": ["hysteria2"],
}


@dataclass(frozen=True)
class DocumentPage:
    path: str
    title: str
    lang: str
    section: str
    headings: list[str]
    fields: list[str]
    body_text: str
    examples: list[str]
    source_url: str
    lastmod: str
    field_availability: dict[str, list[AvailabilityNote]] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    score: int
    page: DocumentPage
    snippet: str
    matched_fields: list[str]
    matched_headings: list[str]


@dataclass(frozen=True)
class DocsIndex:
    pages: list[DocumentPage]
    lang: str
    version: str
    source: str
    fetched_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "pages": [asdict(page) for page in self.pages],
                "lang": self.lang,
                "version": self.version,
                "source": self.source,
                "fetched_at": self.fetched_at,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, value: str) -> "DocsIndex":
        raw = json.loads(value)
        return cls(
            pages=[document_page_from_dict(page) for page in raw["pages"]],
            lang=raw["lang"],
            version=raw["version"],
            source=raw["source"],
            fetched_at=raw["fetched_at"],
        )

    def sections(self) -> list[str]:
        return sorted({page.section for page in self.pages})

    def find_page(self, query: str) -> DocumentPage | None:
        path = normalize_doc_path(query)
        if not path:
            path = "home"
        candidates = path_candidates(path)
        for candidate in candidates:
            for page in self.pages:
                if page.path == candidate:
                    return page
        suffix_matches = [page for page in self.pages if page.path.endswith(f"/{path}") or page.path.endswith(path)]
        return suffix_matches[0] if len(suffix_matches) == 1 else None

    def list_pages(self, section: str = "") -> list[DocumentPage]:
        section = section.strip().lower().replace("_", "-")
        if not section:
            return sorted(self.pages, key=lambda page: page.path)
        return sorted(
            [page for page in self.pages if page.section.replace("_", "-") == section or page.path.startswith(section)],
            key=lambda page: page.path,
        )

    def search(self, query: str, section: str = "", limit: int = 20) -> list[tuple[int, DocumentPage]]:
        return [(result.score, result.page) for result in self.search_results(query=query, section=section, limit=limit)]

    def search_results(self, query: str, section: str = "", limit: int = 20) -> list[SearchResult]:
        tokens = expand_query_tokens(query)
        if not tokens:
            return []
        section_filter = normalize_section_filter(section)
        results: list[SearchResult] = []
        for page in self.pages:
            if section_filter and page.section.replace("_", "-") != section_filter:
                continue
            result = score_page(page, tokens, query)
            if result is not None:
                results.append(result)
        results.sort(key=lambda result: (-result.score, path_rank(result.page), result.page.path))
        return results[:limit]


def path_candidates(path: str) -> list[str]:
    normalized = normalize_query_path(path)
    variants = [
        normalized,
        f"configuration/{normalized}",
        normalized.replace("_", "-"),
        normalized.replace("-", "_"),
    ]
    if normalized.startswith("configuration/"):
        variants.append(normalized.removeprefix("configuration/"))
    return dedupe([variant.strip("/") for variant in variants if variant.strip("/")])


def normalize_query_path(value: str) -> str:
    return normalize_doc_path(value).lower().replace(".", "/").replace("_", "-").strip("/")


def normalize_section_filter(value: str) -> str:
    section = normalize_query_path(value)
    if section.startswith("configuration/"):
        parts = section.split("/")
        if len(parts) > 1:
            return parts[1]
    return section


def expand_query_tokens(query: str) -> list[str]:
    raw_tokens = tokenize(query)
    expanded: list[str] = []
    for token in raw_tokens:
        normalized = token.lower().replace("_", "-")
        expanded.append(normalized)
        expanded.extend(part for part in normalized.replace(".", "-").split("-") if part)
        expanded.extend(QUERY_ALIASES.get(normalized, []))
    return dedupe(expanded)


def score_page(page: DocumentPage, tokens: list[str], query: str) -> SearchResult | None:
    phrase = normalize_text_for_search(query)
    title = normalize_text_for_search(page.title)
    path = normalize_text_for_search(page.path)
    section = normalize_text_for_search(page.section)
    body = normalize_text_for_search(page.body_text)
    availability = normalize_text_for_search(
        " ".join(note.note for notes in page.field_availability.values() for note in notes)
    )

    matched_fields = matched_values(page.fields, tokens, phrase)
    matched_headings = matched_values(page.headings, tokens, phrase)

    score = 0
    if phrase and phrase in title:
        score += 80
    if phrase and phrase in path:
        score += 70
    if phrase and phrase in normalize_text_for_search(" ".join(page.fields)):
        score += 45
    if phrase and phrase in normalize_text_for_search(" ".join(page.headings)):
        score += 35

    for token in tokens:
        token_score = 0
        if token == title:
            token_score += 60
        elif token in title:
            token_score += 28
        if token == page.section.replace("_", "-"):
            token_score += 24
        elif token in section:
            token_score += 12
        if token in path:
            token_score += 22
        if any(token == normalize_text_for_search(field) for field in page.fields):
            token_score += 40
        elif any(token in normalize_text_for_search(field) for field in page.fields):
            token_score += 18
        if any(token == normalize_text_for_search(heading) for heading in page.headings):
            token_score += 28
        elif any(token in normalize_text_for_search(heading) for heading in page.headings):
            token_score += 12
        if token in availability:
            token_score += 8
        if token in body:
            token_score += 2
        score += token_score

    if not matched_fields and not matched_headings and score <= 0:
        return None

    snippet = best_snippet(page, tokens, matched_fields, matched_headings)
    return SearchResult(
        score=score,
        page=page,
        snippet=snippet,
        matched_fields=matched_fields,
        matched_headings=matched_headings,
    )


def normalize_text_for_search(value: str) -> str:
    return " ".join(tokenize(value.replace("/", " ").replace("_", " ").replace("-", " ").replace(".", " ")))


def matched_values(values: list[str], tokens: list[str], phrase: str) -> list[str]:
    matches: list[str] = []
    for value in values:
        normalized = normalize_text_for_search(value)
        if phrase and phrase in normalized:
            matches.append(value)
            continue
        if any(token in normalized for token in tokens):
            matches.append(value)
    return matches[:8]


def best_snippet(page: DocumentPage, tokens: list[str], fields: list[str], headings: list[str]) -> str:
    field_snippet = snippet_after_anchor(page.body_text, fields)
    if field_snippet:
        return field_snippet
    heading_snippet = snippet_after_anchor(page.body_text, headings)
    if heading_snippet:
        return heading_snippet
    for line in clean_snippet_lines(page.body_text):
        normalized = normalize_text_for_search(line)
        if any(token in normalized for token in tokens):
            return truncate_snippet(line)
    return truncate_snippet(page.body_text)


def snippet_after_anchor(body_text: str, anchors: list[str]) -> str:
    if not anchors:
        return ""
    lines = clean_snippet_lines(body_text)
    normalized_anchors = {normalize_text_for_search(anchor) for anchor in anchors}
    for index, line in enumerate(lines):
        if normalize_text_for_search(line) not in normalized_anchors:
            continue
        context = " ".join(lines[index : index + 4])
        return truncate_snippet(context)
    return ""


def clean_snippet_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def truncate_snippet(value: str, max_chars: int = 260) -> str:
    text = " ".join(value.split())
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rsplit(' ', 1)[0]}..."


def path_rank(page: DocumentPage) -> int:
    if page.path.startswith("configuration/"):
        return 0
    if page.section in {"installation", "migration"}:
        return 2
    return 1


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def cache_path(lang: str, version: str) -> Path:
    return INDEX_CACHE_DIR / f"docs-{lang}-{version}.json"


def load_cached_index(lang: str = "en", version: str = "latest") -> DocsIndex | None:
    path = cache_path(lang, version)
    if not path.exists():
        return None
    return DocsIndex.from_json(path.read_text(encoding="utf-8"))


def save_cached_index(index: DocsIndex) -> None:
    path = cache_path(index.lang, index.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(index.to_json(), encoding="utf-8")


def document_page_from_dict(raw: dict[str, object]) -> DocumentPage:
    availability_raw = raw.get("field_availability", {})
    field_availability: dict[str, list[AvailabilityNote]] = {}
    if isinstance(availability_raw, dict):
        for field_name, notes_raw in availability_raw.items():
            if not isinstance(field_name, str) or not isinstance(notes_raw, list):
                continue
            notes: list[AvailabilityNote] = []
            for note_raw in notes_raw:
                if isinstance(note_raw, dict):
                    notes.append(
                        AvailabilityNote(
                            kind=str(note_raw.get("kind", "")),
                            version=str(note_raw.get("version", "")),
                            note=str(note_raw.get("note", "")),
                        )
                    )
            field_availability[field_name] = notes

    return DocumentPage(
        path=str(raw["path"]),
        title=str(raw["title"]),
        lang=str(raw["lang"]),
        section=str(raw["section"]),
        headings=string_list(raw.get("headings")),
        fields=string_list(raw.get("fields")),
        body_text=str(raw["body_text"]),
        examples=string_list(raw.get("examples")),
        source_url=str(raw["source_url"]),
        lastmod=str(raw["lastmod"]),
        field_availability=field_availability,
    )


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def load_or_refresh_index(lang: str = "en", version: str = "latest") -> DocsIndex:
    cached = load_cached_index(lang, version)
    if cached is not None:
        return cached
    index = refresh_index(lang=lang, version=version)
    save_cached_index(index)
    return index


def refresh_index(lang: str = "en", version: str = "latest") -> DocsIndex:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    sitemap_response = session.get(SITEMAP_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    sitemap_response.raise_for_status()
    urls = parse_sitemap(sitemap_response.text, lang=lang)

    pages: list[DocumentPage] = []
    for url, lastmod in urls[:REFRESH_PAGE_LIMIT]:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        page = document_page_from_html(response.text, url=url, lang=lang, lastmod=lastmod)
        if page.body_text:
            pages.append(page)

    return DocsIndex(
        pages=pages,
        lang=lang,
        version=version,
        source=SITEMAP_URL,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def parse_sitemap(xml_text: str, lang: str = "en") -> list[tuple[str, str]]:
    root = ET.fromstring(xml_text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[tuple[str, str]] = []
    for url_node in root.findall("sm:url", namespace):
        loc = url_node.findtext("sm:loc", default="", namespaces=namespace)
        lastmod = url_node.findtext("sm:lastmod", default="", namespaces=namespace)
        if not loc:
            continue
        if lang == "en" and "/zh/" in loc:
            continue
        if lang == "zh" and "/zh/" not in loc:
            continue
        urls.append((loc, lastmod))
    return urls


def document_page_from_html(html: str, *, url: str, lang: str, lastmod: str = "") -> DocumentPage:
    title, headings_with_level, body_text, examples, field_availability = extract_article(html)
    path = normalize_doc_path(url) or "home"
    headings = [heading for _, heading in headings_with_level]
    fields = [heading for level, heading in headings_with_level if level >= 4]
    if not title:
        title = path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title() or "Home"
    return DocumentPage(
        path=path,
        title=title,
        lang=lang,
        section=path_to_section(path),
        headings=headings,
        fields=fields,
        body_text=body_text,
        examples=examples[:10],
        source_url=url,
        lastmod=lastmod,
        field_availability=field_availability,
    )
