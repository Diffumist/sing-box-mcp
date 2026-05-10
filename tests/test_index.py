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
