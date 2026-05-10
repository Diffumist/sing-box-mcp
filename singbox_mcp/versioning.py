"""sing-box version parsing and availability checks."""

from __future__ import annotations

from dataclasses import dataclass
import re

VERSION_RE = re.compile(r"^(?:v)?(\d+)\.(\d+)(?:\.(\d+))?$")
AVAILABILITY_RE = re.compile(
    r"\b(Since|Deprecated in|Removed in|Changes in)\s+sing-box\s+v?(\d+\.\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class SingBoxVersion:
    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class AvailabilityNote:
    kind: str
    version: str
    note: str


def parse_version(value: str) -> SingBoxVersion | None:
    match = VERSION_RE.match(value.strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return SingBoxVersion(int(major), int(minor), int(patch or "0"))


def parse_availability_note(value: str) -> AvailabilityNote | None:
    match = AVAILABILITY_RE.search(value)
    if match is None:
        return None
    kind_raw, version = match.groups()
    normalized_kind = kind_raw.lower()
    if normalized_kind == "since":
        kind = "since"
    elif normalized_kind == "deprecated in":
        kind = "deprecated"
    elif normalized_kind == "removed in":
        kind = "removed"
    else:
        kind = "changed"
    parsed = parse_version(version)
    if parsed is None:
        return None
    return AvailabilityNote(kind=kind, version=str(parsed), note=value.strip())


def is_explicit_version(value: str) -> bool:
    return parse_version(value) is not None


def availability_status(notes: list[AvailabilityNote], target_version: str) -> str:
    target = parse_version(target_version)
    if target is None:
        return "available in latest docs"

    since_versions = [parse_version(note.version) for note in notes if note.kind == "since"]
    deprecated_versions = [parse_version(note.version) for note in notes if note.kind == "deprecated"]
    removed_versions = [parse_version(note.version) for note in notes if note.kind == "removed"]
    known_since = [version for version in since_versions if version is not None]
    known_deprecated = [version for version in deprecated_versions if version is not None]
    known_removed = [version for version in removed_versions if version is not None]

    if known_removed:
        earliest_removed = min(known_removed)
        if target >= earliest_removed:
            return f"removed in sing-box {earliest_removed}"
    if known_since:
        newest_since = max(known_since)
        if target < newest_since:
            return f"not available before sing-box {newest_since}"
    if known_deprecated:
        earliest_deprecated = min(known_deprecated)
        if target >= earliest_deprecated:
            return f"deprecated in sing-box {earliest_deprecated}"
    return f"available in sing-box {target}"
