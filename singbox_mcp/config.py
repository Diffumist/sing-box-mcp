"""Configuration constants for sing-box-mcp."""

from __future__ import annotations

import os
from pathlib import Path

DOCS_BASE_URL = "https://sing-box.sagernet.org/"
SITEMAP_URL = f"{DOCS_BASE_URL}sitemap.xml"

DEFAULT_VERSION = "latest"
DEFAULT_LANG = "en"
SUPPORTED_LANGS = {"en", "zh"}

DEFAULT_LIMIT = 20
MAX_LIMIT = 50

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = "sing-box-mcp/0.1.0 (+https://sing-box.sagernet.org/)"

REFRESH_PAGE_LIMIT = 250

INDEX_CACHE_DIR = Path(os.environ.get("SINGBOX_MCP_CACHE_DIR", Path.home() / ".cache" / "sing-box-mcp"))
