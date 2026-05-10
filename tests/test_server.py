from __future__ import annotations

from singbox_mcp.index import DocsIndex, DocumentPage
from singbox_mcp.server import handle_singbox_docs
from singbox_mcp.versioning import AvailabilityNote


def fixture_index() -> DocsIndex:
    return DocsIndex(
        pages=[
            DocumentPage(
                path="configuration/outbound/hysteria2",
                title="Hysteria2",
                lang="en",
                section="outbound",
                headings=["Structure", "Fields", "server", "tls"],
                fields=["server", "tls"],
                body_text="Hysteria2 outbound configuration. The server address. TLS configuration.",
                examples=['{"type": "hysteria2", "server": "127.0.0.1"}'],
                source_url="https://sing-box.sagernet.org/configuration/outbound/hysteria2/",
                lastmod="2026-04-28",
                field_availability={
                    "tls": [AvailabilityNote(kind="since", version="1.14.0", note="Since sing-box 1.14.0")],
                },
            ),
            DocumentPage(
                path="configuration/dns/server/https",
                title="HTTPS",
                lang="en",
                section="dns",
                headings=["Structure", "Fields"],
                fields=["server", "detour"],
                body_text="DNS over HTTPS server configuration.",
                examples=[],
                source_url="https://sing-box.sagernet.org/configuration/dns/server/https/",
                lastmod="2026-04-28",
            ),
        ],
        lang="en",
        version="latest",
        source="https://sing-box.sagernet.org/sitemap.xml",
        fetched_at="2026-05-10T00:00:00+00:00",
    )


def test_search_routes_to_index() -> None:
    response = handle_singbox_docs("search", query="hysteria2", version="1.14.0", docs_index=fixture_index())

    assert "Results for" in response
    assert "Target sing-box version: 1.14.0" in response
    assert "configuration/outbound/hysteria2" in response
    assert "Source: https://sing-box.sagernet.org/configuration/outbound/hysteria2/" in response


def test_info_returns_page_details() -> None:
    response = handle_singbox_docs("info", query="outbound/hysteria2", version="1.14.0", docs_index=fixture_index())

    assert "Page: Hysteria2" in response
    assert "Fields:" in response
    assert "- server: available in sing-box 1.14.0" in response


def test_info_marks_fields_not_available_for_older_target_versions() -> None:
    response = handle_singbox_docs("info", query="outbound/hysteria2", version="1.13.0", docs_index=fixture_index())

    assert "- tls: not available before sing-box 1.14.0; Since sing-box 1.14.0" in response


def test_list_filters_by_section() -> None:
    response = handle_singbox_docs("list", section="dns", docs_index=fixture_index())

    assert "configuration/dns/server/https" in response
    assert "configuration/outbound/hysteria2" not in response


def test_examples_return_code_blocks() -> None:
    response = handle_singbox_docs("examples", query="hysteria2", version="1.14.0", docs_index=fixture_index())

    assert "Official examples" in response
    assert '{"type": "hysteria2"' in response


def test_content_queries_require_explicit_version() -> None:
    response = handle_singbox_docs("info", query="outbound/hysteria2", docs_index=fixture_index())

    assert "Missing target sing-box version" in response
    assert 'version="1.14.0"' in response


def test_invalid_action_includes_examples() -> None:
    response = handle_singbox_docs("bad", docs_index=fixture_index())

    assert "Invalid action" in response
    assert 'singbox_docs(action="search"' in response
