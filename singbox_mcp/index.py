"""Documentation index loading, refreshing, and querying."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

from .config import INDEX_CACHE_DIR, REFRESH_PAGE_LIMIT, REQUEST_TIMEOUT_SECONDS, SITEMAP_URL, USER_AGENT
from .utils import extract_article, normalize_doc_path, path_to_section, summarize_text, tokenize
from .versioning import AvailabilityNote


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
        candidates = [
            path,
            f"configuration/{path}",
            path.replace("_", "-"),
            path.replace("-", "_"),
        ]
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
        tokens = tokenize(query)
        if not tokens:
            return []
        section_filter = section.strip().lower().replace("_", "-")
        scored: list[tuple[int, DocumentPage]] = []
        for page in self.pages:
            if section_filter and page.section.replace("_", "-") != section_filter:
                continue
            score = score_page(page, tokens, query)
            if score > 0:
                scored.append((score, page))
        scored.sort(key=lambda item: (-item[0], item[1].path))
        return scored[:limit]


def score_page(page: DocumentPage, tokens: list[str], query: str) -> int:
    title = page.title.lower()
    path = page.path.lower()
    headings = " ".join(page.headings).lower()
    fields = " ".join(page.fields).lower()
    availability = " ".join(note.note for notes in page.field_availability.values() for note in notes).lower()
    body = page.body_text.lower()
    phrase = query.strip().lower()

    score = 0
    if phrase and phrase in title:
        score += 30
    if phrase and phrase in path:
        score += 20
    for token in tokens:
        if token in title:
            score += 10
        if token in path:
            score += 8
        if token in fields:
            score += 6
        if token in availability:
            score += 5
        if token in headings:
            score += 4
        if token in body:
            score += 1
    return score


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
        body_text=summarize_text(body_text, max_chars=8000),
        examples=examples[:10],
        source_url=url,
        lastmod=lastmod,
        field_availability=field_availability,
    )
