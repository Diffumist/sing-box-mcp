"""Text extraction and formatting helpers."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse

from .config import DOCS_BASE_URL
from .versioning import AvailabilityNote, parse_availability_note

_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+")


class ArticleTextParser(HTMLParser):
    """Extract model-friendly text from a MkDocs Material article."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.article_depth = 0
        self.in_article = False
        self.pre_depth = 0
        self.heading_level = 0
        self.heading_id = ""
        self.capture_admonition_title = False
        self.in_admonition = False
        self.current_admonition_note: AvailabilityNote | None = None
        self.heading_buffer: list[str] = []
        self.admonition_title_buffer: list[str] = []
        self.code_buffer: list[str] = []
        self.body_parts: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.current_field = ""
        self.field_ids: dict[str, str] = {}
        self.pending_anchor_notes: list[tuple[str, AvailabilityNote]] = []
        self.field_availability: dict[str, list[AvailabilityNote]] = {}
        self.examples: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "article":
            self.in_article = True

        if not self.in_article:
            return

        if tag in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.body_parts.append("\n")
        class_name = attr_map.get("class") or ""
        if tag == "div" and "admonition" in class_name:
            self.in_admonition = True
            self.current_admonition_note = None
        if tag == "pre":
            self.pre_depth += 1
            self.code_buffer = []
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_level = int(tag[1])
            self.heading_id = attr_map.get("id") or ""
            self.heading_buffer = []
        if tag == "p" and "admonition-title" in class_name:
            self.capture_admonition_title = True
            self.admonition_title_buffer = []
        href = attr_map.get("href") or ""
        if tag == "a" and href.startswith("#__codelineno"):
            self.code_buffer.append("")
        elif tag == "a" and href.startswith("#") and self.current_admonition_note is not None:
            self.pending_anchor_notes.append((href[1:], self.current_admonition_note))

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article:
            return

        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.body_parts.append("\n")
        if tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
            code = clean_code("".join(self.code_buffer))
            if code:
                self.examples.append(code)
            self.code_buffer = []
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading_level:
            heading = clean_inline_text("".join(self.heading_buffer))
            if heading:
                self.headings.append((self.heading_level, heading))
                if self.heading_level == 1 and not self.title:
                    self.title = heading
                if self.heading_level >= 4:
                    self.current_field = heading
                    if self.heading_id:
                        self.field_ids[self.heading_id] = heading
                else:
                    self.current_field = ""
            self.heading_level = 0
            self.heading_id = ""
            self.heading_buffer = []
        if tag == "p" and self.capture_admonition_title:
            note_text = clean_inline_text("".join(self.admonition_title_buffer))
            note = parse_availability_note(note_text)
            if note is not None:
                self.current_admonition_note = note
                if self.current_field:
                    self.field_availability.setdefault(self.current_field, []).append(note)
            self.capture_admonition_title = False
            self.admonition_title_buffer = []
        if tag == "div" and self.in_admonition:
            self.in_admonition = False
            self.current_admonition_note = None
        if tag == "article":
            self.in_article = False

    def handle_data(self, data: str) -> None:
        if not self.in_article:
            return
        if self.pre_depth:
            self.code_buffer.append(data)
            return
        self.body_parts.append(data)
        if self.heading_level:
            self.heading_buffer.append(data)
        if self.capture_admonition_title:
            self.admonition_title_buffer.append(data)

    def result(self) -> tuple[str, list[tuple[int, str]], str, list[str], dict[str, list[AvailabilityNote]]]:
        for field_id, note in self.pending_anchor_notes:
            field_name = self.field_ids.get(field_id)
            if field_name is not None:
                notes = self.field_availability.setdefault(field_name, [])
                if note not in notes:
                    notes.append(note)
        body_text = clean_body_text("".join(self.body_parts))
        return self.title, self.headings, body_text, self.examples, self.field_availability


def clean_inline_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip()


def clean_body_text(value: str) -> str:
    lines = [clean_inline_text(line) for line in value.splitlines()]
    text = "\n".join(line for line in lines if line)
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def clean_code(value: str) -> str:
    lines = [line.rstrip() for line in value.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def extract_article(html: str) -> tuple[str, list[tuple[int, str]], str, list[str], dict[str, list[AvailabilityNote]]]:
    parser = ArticleTextParser()
    parser.feed(html)
    return parser.result()


def normalize_doc_path(value: str) -> str:
    raw = value.strip()
    if raw.startswith(DOCS_BASE_URL):
        raw = urlparse(raw).path
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    raw = raw.strip("/")
    if raw.startswith("zh/"):
        raw = raw[3:]
    if raw.endswith("/index.html"):
        raw = raw[: -len("/index.html")]
    return raw.strip("/")


def path_to_section(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "home"
    if parts[0] == "configuration" and len(parts) > 1:
        return parts[1]
    return parts[0]


def tokenize(value: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(value)]


def clamp_limit(limit: int) -> int:
    return max(1, min(limit, 50))


def summarize_text(value: str, max_chars: int = 1800) -> str:
    if len(value) <= max_chars:
        return value
    shortened = value[:max_chars].rsplit("\n", 1)[0].strip()
    return f"{shortened}\n..."


def format_bullets(values: Iterable[str], limit: int) -> str:
    items = list(values)[:limit]
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)
