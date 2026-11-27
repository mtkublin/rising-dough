"""E2E: the Today legend glyphs are painted like their bar segments; afford fits 13 characters.

T-UR94: spent and committed cells take the bar's colour, left takes the remainder run's colour,
light and dark, at desktop and phone width. T-UR87: the afford field holds "12,345,678.00".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import today
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_COLOR_JS = "(el) => getComputedStyle(el).color"
_CLIPPED_JS = "(el) => [el.scrollWidth, el.clientWidth]"
_SIZES = ((1440, 900), (375, 812))


def _seed(base_url: str, db_path: Path, page: Page) -> None:
    post = page.request.post
    assert post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "5000.00"},
    ).ok
    assert post(f"{base_url}/categories", form={"name": "Rent", "direction": "expense"}).ok
    category_id = db_probe.category_id(db_path, "Rent")
    assert post(f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}).ok


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("viewport", _SIZES)
def test_legend_glyphs_match_their_bar_segments(
    live_server: tuple[str, Path],
    page: Page,
    scheme: str,
    viewport: tuple[int, int],
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.emulate_media(color_scheme="dark" if scheme == "dark" else "light")
    page.goto(f"{base_url}/today")
    bar = to_playwright(page, today.spent_bar).evaluate(_COLOR_JS)
    remainder = to_playwright(page, today.bar_remainder).evaluate(_COLOR_JS)
    assert remainder != bar, "the left run is told apart from spent and committed"
    assert to_playwright(page, today.legend_glyph("spent")).evaluate(_COLOR_JS) == bar
    assert to_playwright(page, today.legend_glyph("committed")).evaluate(_COLOR_JS) == bar
    assert to_playwright(page, today.legend_glyph("left")).evaluate(_COLOR_JS) == remainder


def test_afford_input_holds_13_characters_at_375(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _db_path = live_server
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(f"{base_url}/today")
    afford = to_playwright(page, today.afford_amount)
    afford.fill("12,345,678.00")
    expect(afford).to_have_value("12,345,678.00")
    scroll, client = afford.evaluate(_CLIPPED_JS)
    assert scroll <= client, f"afford input clips 13 characters: {scroll} > {client}"
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
