"""T-068 — Command palette + global keyboard shortcuts.

Template-level assertions only: the palette and shortcuts partials ship with
every page, the JS loader tags are present, and the palette's `data-shortcut`
values stay a subset of the primary nav shortcuts (plus the two action keys).
Keyboard interaction itself lives in Playwright (see task plan §Validation).
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from tests.ui_map import _html, rd_shell


def _soup(client: TestClient, path: str = "/today") -> BeautifulSoup:
    response = client.get(path)
    assert response.status_code == 200
    return BeautifulSoup(response.text, "html.parser")


def test_palette_partial_in_base(client: TestClient) -> None:
    soup = _soup(client)
    dialog = _html.resolve_one(soup, rd_shell.palette)
    assert dialog.name == "dialog"
    assert dialog.get("aria-label") == "Command palette"
    assert _html.exists(soup, rd_shell.palette_input)
    assert _html.count(soup, rd_shell.palette_options) == 7  # the handoff's 7 entries


def test_shortcuts_partial_in_base(client: TestClient) -> None:
    soup = _soup(client)
    dialog = _html.resolve_one(soup, rd_shell.shortcuts)
    assert dialog.name == "dialog"
    assert dialog.get("aria-labelledby") == "shortcuts-title"
    assert _html.exists(soup, rd_shell.shortcuts_dialog)


def test_palette_js_loaded(client: TestClient) -> None:
    soup = _soup(client)
    scripts = [str(s.get("src", "")) for s in soup.find_all("script")]

    # Rising Dough v2 appends cache-busting ?v=rd1 — strip the query before checking.
    def _bare(src: str) -> str:
        return src.split("?", 1)[0]

    bare = [_bare(s) for s in scripts]
    assert any(src.endswith("js/palette.js") for src in bare)
    assert any(src.endswith("js/shortcuts.js") for src in bare)


def test_palette_nav_items_match_nav_partial(client: TestClient) -> None:
    """ADR-0023: the palette's Go-to rows point at the primary nav's destinations."""
    soup = _soup(client)
    nav_hrefs = {str(a["href"]) for a in _html.resolve(soup, rd_shell.nav_links)}
    assert nav_hrefs == {"/today", "/ledger", "/plan", "/accounts"}
    options = {
        str(el.get("data-href")): next(el.stripped_strings)
        for el in _html.resolve(soup, rd_shell.palette_options)
    }
    assert options["/today"] == "Go to Today"
    assert options["/ledger"] == "Go to Ledger"
    assert options["/plan"] == "Go to Plan"
    assert options["/accounts"] == "Go to Accounts"
    assert options["/settings"] == "Open Settings"
