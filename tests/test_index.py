from __future__ import annotations

from singbox_mcp.index import DocsIndex, DocumentPage, document_page_from_html, parse_sitemap


def test_parse_sitemap_filters_language() -> None:
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://sing-box.sagernet.org/configuration/dns/</loc><lastmod>2026-04-28</lastmod></url>
      <url><loc>https://sing-box.sagernet.org/zh/configuration/dns/</loc><lastmod>2026-04-28</lastmod></url>
    </urlset>
    """

    assert parse_sitemap(sitemap, lang="en") == [
        ("https://sing-box.sagernet.org/configuration/dns/", "2026-04-28")
    ]
    assert parse_sitemap(sitemap, lang="zh") == [
        ("https://sing-box.sagernet.org/zh/configuration/dns/", "2026-04-28")
    ]


def test_document_page_from_html_extracts_article_text_headings_and_examples() -> None:
    html = """
    <html><body>
      <nav>Navigation noise</nav>
      <article class="md-content__inner md-typeset">
        <h1>Hysteria2</h1>
        <div class="admonition quote">
          <p class="admonition-title">Changes in sing-box 1.13.0</p>
          <p><a href="#server">server</a></p>
        </div>
        <h3 id="structure">Structure</h3>
        <pre><code>{
          "type": "hysteria2",
          "server": "127.0.0.1"
        }</code></pre>
        <h3 id="fields">Fields</h3>
        <h4 id="server">server</h4>
        <div class="admonition question">
          <p class="admonition-title">Since sing-box 1.14.0</p>
        </div>
        <p>The server address.</p>
        <h4 id="old_field">old_field</h4>
        <div class="admonition warning">
          <p class="admonition-title">Deprecated in sing-box 1.11.0</p>
        </div>
        <h4 id="removed_field">removed_field</h4>
        <div class="admonition failure">
          <p class="admonition-title">Removed in sing-box 1.14.0</p>
        </div>
      </article>
    </body></html>
    """

    page = document_page_from_html(
        html,
        url="https://sing-box.sagernet.org/configuration/outbound/hysteria2/",
        lang="en",
        lastmod="2026-04-28",
    )

    assert page.title == "Hysteria2"
    assert page.path == "configuration/outbound/hysteria2"
    assert page.section == "outbound"
    assert "server" in page.fields
    assert page.field_availability["server"][0].kind == "since"
    assert page.field_availability["server"][0].version == "1.14.0"
    assert page.field_availability["server"][1].kind == "changed"
    assert page.field_availability["old_field"][0].kind == "deprecated"
    assert page.field_availability["removed_field"][0].kind == "removed"
    assert "The server address." in page.body_text
    assert page.examples[0].startswith("{")


def test_document_page_from_html_preserves_full_body_text_for_indexing() -> None:
    long_prefix = "x" * 8500
    html = f"""
    <html><body>
      <article class="md-content__inner md-typeset">
        <h1>Long Page</h1>
        <p>{long_prefix}</p>
        <p>late_search_marker</p>
      </article>
    </body></html>
    """

    page = document_page_from_html(
        html,
        url="https://sing-box.sagernet.org/configuration/dns/long-page/",
        lang="en",
    )

    assert "late_search_marker" in page.body_text
    assert not page.body_text.endswith("...")


def test_docs_index_search_and_find_page() -> None:
    index = DocsIndex(
        pages=[
            DocumentPage(
                path="configuration/outbound/hysteria2",
                title="Hysteria2",
                lang="en",
                section="outbound",
                headings=["Structure", "Fields", "server"],
                fields=["server"],
                body_text="Hysteria2 outbound server address.",
                examples=[],
                source_url="https://sing-box.sagernet.org/configuration/outbound/hysteria2/",
                lastmod="2026-04-28",
            )
        ],
        lang="en",
        version="latest",
        source="https://sing-box.sagernet.org/sitemap.xml",
        fetched_at="2026-05-10T00:00:00+00:00",
    )

    assert index.find_page("outbound/hysteria2").title == "Hysteria2"
    assert index.search("hysteria2 server", section="outbound", limit=5)[0][1].path == (
        "configuration/outbound/hysteria2"
    )


def test_search_results_include_field_matches_and_snippets() -> None:
    index = DocsIndex(
        pages=[
            DocumentPage(
                path="configuration/inbound/tun",
                title="Tun",
                lang="en",
                section="inbound",
                headings=["Structure", "Fields", "server_port"],
                fields=["server_port"],
                body_text="Tun\nFields\nserver_port\nThe listen port used by the inbound.",
                examples=[],
                source_url="https://sing-box.sagernet.org/configuration/inbound/tun/",
                lastmod="2026-04-28",
            )
        ],
        lang="en",
        version="latest",
        source="https://sing-box.sagernet.org/sitemap.xml",
        fetched_at="2026-05-10T00:00:00+00:00",
    )

    result = index.search_results("server_port", limit=1)[0]

    assert result.page.path == "configuration/inbound/tun"
    assert result.matched_fields == ["server_port"]
    assert "The listen port used by the inbound." in result.snippet


def test_query_normalization_supports_dotted_paths_and_aliases() -> None:
    index = DocsIndex(
        pages=[
            DocumentPage(
                path="configuration/dns/server/https",
                title="HTTPS",
                lang="en",
                section="dns",
                headings=["DNS over HTTPS", "server"],
                fields=["server"],
                body_text="DNS over HTTPS server configuration.",
                examples=[],
                source_url="https://sing-box.sagernet.org/configuration/dns/server/https/",
                lastmod="2026-04-28",
            )
        ],
        lang="en",
        version="latest",
        source="https://sing-box.sagernet.org/sitemap.xml",
        fetched_at="2026-05-10T00:00:00+00:00",
    )

    assert index.find_page("dns.server.https").path == "configuration/dns/server/https"
    assert index.search_results("doh", limit=1)[0].page.path == "configuration/dns/server/https"


def test_search_rerank_prefers_configuration_pages() -> None:
    index = DocsIndex(
        pages=[
            DocumentPage(
                path="installation/package-manager",
                title="Package Manager",
                lang="en",
                section="installation",
                headings=["DNS"],
                fields=[],
                body_text="dns dns dns dns dns outbound",
                examples=[],
                source_url="https://sing-box.sagernet.org/installation/package-manager/",
                lastmod="2026-04-28",
            ),
            DocumentPage(
                path="configuration/dns/server/https",
                title="HTTPS",
                lang="en",
                section="dns",
                headings=["Fields"],
                fields=["server"],
                body_text="DNS server configuration.",
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

    assert index.search_results("dns server", limit=2)[0].page.path == "configuration/dns/server/https"
