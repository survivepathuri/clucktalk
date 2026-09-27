"""MCP App card contract (MCP Apps spec 2026-01-26; docs/DESIGN.md §14), over the real HTTP wire."""

from __future__ import annotations

import re

from clucktalk.server.cards import FARM_STATUS_URI

APP_MIME = "text/html;profile=mcp-app"
EXTERNAL = (
    re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", re.I),
    re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.I),
    re.compile(r"@import", re.I),
    re.compile(r"""\bfetch\s*\(|XMLHttpRequest|WebSocket\s*\(|EventSource\s*\(""", re.I),
)


def _tools(live) -> dict:
    sid, _ = live.initialize()
    return {t["name"]: t for t in live.call(sid, "tools/list")["result"]["tools"]}


def _read_card(live) -> dict:
    sid, _ = live.initialize()
    body = live.call(sid, "resources/read", {"uri": FARM_STATUS_URI})
    assert "result" in body, body
    (content,) = body["result"]["contents"]
    return content


def test_get_farm_status_declares_its_card(live):
    assert _tools(live)["get_farm_status"]["_meta"]["ui"] == {"resourceUri": FARM_STATUS_URI}


def test_tools_without_a_card_declare_none(live):
    """Declare only what you honor: no resourceUri on tools that have no card yet."""
    tools = _tools(live)
    for name in ("plan_feed", "get_help"):
        assert "ui" not in (tools[name].get("_meta") or {}), name


def test_card_is_listed_with_the_app_mime_type(live):
    sid, _ = live.initialize()
    listed = {r["uri"]: r for r in live.call(sid, "resources/list")["result"]["resources"]}
    assert listed[FARM_STATUS_URI]["mimeType"] == APP_MIME


def test_card_read_is_a_self_contained_html5_document(live):
    content = _read_card(live)
    assert content["uri"] == FARM_STATUS_URI
    assert content["mimeType"] == APP_MIME
    html = content["text"]
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in html
    for pattern in EXTERNAL:  # the spec's default CSP allows no network access at all
        assert not pattern.search(html), pattern.pattern


def test_card_bundles_the_telugu_font_inline(live):
    html = _read_card(live)["text"]
    assert html.count("@font-face") == 2
    assert html.count('src: url("data:font/otf;base64,') == 2
    assert '"Noto Sans Telugu CT"' in html


def test_server_stamps_demo_mode_into_the_card(live):
    """The Demo data badge must show on every card in demo mode, including error cards that carry no
    structuredContent, so the server fills the placeholder from its own mode."""
    html = _read_card(live)["text"]
    assert "const SERVER_DEMO = true;" in html
    assert "@SERVER_DEMO@" not in html


def test_card_asks_the_host_for_no_border_and_no_permissions(live):
    meta = _read_card(live)["_meta"]["ui"]
    assert meta == {"prefersBorder": False}  # no csp, no permissions: the restrictive default applies
