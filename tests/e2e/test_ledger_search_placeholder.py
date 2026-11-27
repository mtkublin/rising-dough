"""E2E: the ledger search placeholder fits its field at 375 (LEDGERPH, T-UR74).

At 375 the touch font is 16px (T-UR81), and the search field must hold the whole placeholder
"search description…" with its horizontal padding. At 1440 the search field and the filters
toggle stay on the same row.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from tests.e2e import db_probe
from tests.ui_map import ledger
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e

PHONE: ViewportSize = {"width": 375, "height": 812}
DESKTOP: ViewportSize = {"width": 1440, "height": 900}
FILTERS_TOGGLE = role("button", "filters", exact=True)
PLACEHOLDER = "search description"

# Width the placeholder needs (canvas measure in the input's computed font) against the content
# box the input offers: clientWidth less the horizontal padding.
_PLACEHOLDER_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const cs = getComputedStyle(el);
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
  if ('letterSpacing' in ctx) ctx.letterSpacing = cs.letterSpacing;
  const padding = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  return {
    text: el.placeholder,
    px: parseFloat(cs.fontSize),
    need: ctx.measureText(el.placeholder).width + padding,
    has: el.clientWidth,
  };
}
"""


def _seed(base_url: str, db_path: Path, page: Page) -> None:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert db_probe.account_id(db_path, "Checking")


def _open_ledger(base_url: str, page: Page, viewport: ViewportSize) -> None:
    page.set_viewport_size(viewport)
    page.goto(f"{base_url}/ledger")
    page.wait_for_function("typeof window.htmx === 'object'")
    expect(to_playwright(page, ledger.filter_search)).to_be_visible()


def test_search_placeholder_fits_the_field_at_375(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_ledger(base_url, page, PHONE)
    measured: dict[str, object] = page.evaluate(_PLACEHOLDER_JS, "#f-q")
    assert measured["text"] == PLACEHOLDER
    assert measured["px"] == 16
    need = float(str(measured["need"]))
    has = float(str(measured["has"]))
    assert need <= has, f"placeholder needs {need:.1f}px with padding, field has {has}px"


def test_desktop_filter_row_is_unchanged_at_1440(live_server: tuple[str, Path], page: Page) -> None:
    """At >= 48rem the filters toggle is hidden and the search field stays in the filter row."""
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_ledger(base_url, page, DESKTOP)
    expect(to_playwright(page, FILTERS_TOGGLE)).to_be_hidden()
    search = to_playwright(page, ledger.filter_search).bounding_box()
    category = to_playwright(page, ledger.filter_category).bounding_box()
    assert search is not None
    assert category is not None
    # the search shares the row of the category filter (vertical overlap)
    assert category["y"] < search["y"] + search["height"]
    assert search["y"] < category["y"] + category["height"]
