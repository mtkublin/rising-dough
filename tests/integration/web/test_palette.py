"""T-068 — Command palette + global keyboard shortcuts.

Template-level assertions only: the palette and shortcuts partials ship with
every page, the JS loader tags are present, and the palette's `data-shortcut`
values stay a subset of the primary nav shortcuts (plus the two action keys).
Keyboard interaction itself lives in Playwright (see task plan §Validation).
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient


def _soup(client: TestClient, path: str = "/today") -> BeautifulSoup:
    response = client.get(path)
    assert response.status_code == 200
    return BeautifulSoup(response.text, "html.parser")


def test_palette_partial_in_base(client: TestClient) -> None:
    soup = _soup(client)
    dialog = soup.find("dialog", id="command-palette")
    assert isinstance(dialog, Tag)
    assert dialog.get("aria-modal") == "true"
    assert soup.select_one("#command-palette .palette-input") is not None


def test_shortcuts_partial_in_base(client: TestClient) -> None:
    soup = _soup(client)
    dialog = soup.find("dialog", id="shortcuts-dialog")
    assert isinstance(dialog, Tag)
    assert dialog.get("aria-modal") == "true"


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
    """ADR-0023: the keymap lives in the nav partial. Any palette NAVIGATE row
    must point at a `data-shortcut` the primary nav already exposes. Action
    keys (`n`, `?`) are palette-only and allowed."""
    soup = _soup(client)
    nav_shortcuts = {
        el["data-shortcut"] for el in soup.select("nav [data-shortcut]") if el.get("data-shortcut")
    }
    palette_shortcuts = {
        el["data-shortcut"] for el in soup.select("#command-palette .palette-item[data-shortcut]")
    }
    assert palette_shortcuts, "palette has no shortcut items"
    # Rising Dough v2 collapses Budget + Forecast + Analytics into /plan.
    # Palette may still expose their legacy chords ('g b', 'g f', 'g a' for
    # analytics) during the transition — accept them as action chords.
    v1_action_chords = {"g b", "g f", "g a"}
    allowed = nav_shortcuts | {"n", "?"} | v1_action_chords
    extra = palette_shortcuts - allowed
    assert not extra, f"palette shortcuts not in nav + actions: {extra}"
