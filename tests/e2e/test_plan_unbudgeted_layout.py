"""E2E: the "without a budget" list on Plan/budget lays out like the main table (T-UR75, T-UR80).

At 375 each row is a card: the category chip keeps its shape, the "set budget"
button stays inside the card and nothing leaves it. At 1440 the STATUS column of the list starts
where the main table's does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import plan_budget
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_LISTED = "Entertainment and leisure"  # long: the chip must not be squashed by the status cell
_URL = "/plan?tab=budget&year=2026&month=6"
_PHONE = {"width": 375, "height": 800}
_DESKTOP = {"width": 1440, "height": 900}

# The status cell's own text, and the disclosure's computed box (R24, R25).
_CELL_TEXT_JS = "(cell) => cell.textContent.trim()"
_BOX_JS = """(summary) => {
  const s = getComputedStyle(summary.closest('details'));
  return {
    borders: [s.borderTopWidth, s.borderRightWidth, s.borderBottomWidth, s.borderLeftWidth],
    background: s.backgroundColor,
  };
}"""
_CHIP_JS = """(cell) => {
  const r = cell.firstElementChild.getBoundingClientRect();
  return {w: r.width, h: r.height};
}"""
_OVERFLOW_JS = """(region) => [...region.querySelectorAll('td')]
  .filter((td) => td.scrollWidth > td.clientWidth + 1
    || td.getBoundingClientRect().right > region.getBoundingClientRect().right + 1)
  .map((td) => td.textContent.trim())"""


def _seed(base_url: str, db_path: Path, page: Page) -> None:
    post = page.request.post
    assert post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "5000.00"},
    ).ok
    for name in ("Groceries", _LISTED):
        assert post(f"{base_url}/categories", form={"name": name, "direction": "expense"}).ok
    category_id = db_probe.category_id(db_path, "Groceries")
    assert post(f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}).ok


def _open_list(base_url: str, page: Page) -> None:
    page.goto(f"{base_url}{_URL}")
    page.get_by_text("1 category without a budget").click()
    expect(to_playwright(page, plan_budget.unbudgeted_row(_LISTED))).to_be_visible()


def test_phone_card_keeps_the_chip_and_status_holds_only_the_button(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size(_PHONE)  # type: ignore[arg-type]  # dict is a ViewportSize
    _open_list(base_url, page)

    cells = to_playwright(page, plan_budget.unbudgeted_cells(_LISTED))
    chip: dict[str, float] = cells.nth(0).evaluate(_CHIP_JS)
    main_chip: dict[str, float] = (
        to_playwright(page, plan_budget.row_cells("Groceries")).nth(0).evaluate(_CHIP_JS)
    )
    assert chip["w"] > chip["h"] * 1.5
    bar = cells.nth(1).bounding_box()
    assert bar is not None
    assert bar["width"] > 100
    assert chip["h"] == pytest.approx(main_chip["h"], abs=1)
    status = to_playwright(page, plan_budget.unbudgeted_status_cell(_LISTED))
    assert status.evaluate(_CELL_TEXT_JS) == "set budget"
    region = to_playwright(page, plan_budget.unbudgeted_table_region)
    assert region.evaluate(_OVERFLOW_JS) == []


def test_desktop_status_column_lines_up_with_the_main_table(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size(_DESKTOP)  # type: ignore[arg-type]  # dict is a ViewportSize
    _open_list(base_url, page)

    main = to_playwright(page, plan_budget.row_cells("Groceries")).nth(3).bounding_box()
    listed = to_playwright(page, plan_budget.unbudgeted_cells(_LISTED)).nth(3).bounding_box()
    assert main is not None
    assert listed is not None
    # Both cells are end-aligned in their track: the right edge is the column's edge.
    assert listed["x"] + listed["width"] == pytest.approx(main["x"] + main["width"], abs=2)


@pytest.mark.parametrize("width", [1440, 1024], ids=["1440", "1024"])
def test_every_column_starts_where_the_main_table_column_does(
    live_server: tuple[str, Path], page: Page, width: int
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size({"width": width, "height": 900})
    _open_list(base_url, page)

    main = to_playwright(page, plan_budget.row_cells("Groceries"))
    listed = to_playwright(page, plan_budget.unbudgeted_cells(_LISTED))
    for column in range(5):
        main_box = main.nth(column).bounding_box()
        listed_box = listed.nth(column).bounding_box()
        assert main_box is not None
        assert listed_box is not None
        # Start-aligned cells (category, bar) compare their left edge; end-aligned ones (spent,
        # status, actions) their right edge, which is the column's edge whatever the text width.
        edge = "x" if column < 2 else "right"
        listed_edge = listed_box["x"] + (listed_box["width"] if edge == "right" else 0)
        main_edge = main_box["x"] + (main_box["width"] if edge == "right" else 0)
        assert listed_edge == pytest.approx(main_edge, abs=1), f"column {column}"


@pytest.mark.parametrize("viewport", [_DESKTOP, _PHONE], ids=["1440", "375"])
@pytest.mark.parametrize("tab", ["budget", "year"])
def test_disclosure_has_no_outer_box(
    live_server: tuple[str, Path], page: Page, tab: str, viewport: dict[str, int]
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size(viewport)  # type: ignore[arg-type]  # dict is a ViewportSize
    page.goto(f"{base_url}/plan?tab={tab}&year=2026&month=6")
    summary = page.get_by_text(re.compile(r"without a budget$"))
    expect(summary).to_be_visible()
    box: dict[str, Any] = summary.evaluate(_BOX_JS)
    assert box["borders"] == ["0px", "0px", "0px", "0px"]
    assert box["background"] == "rgba(0, 0, 0, 0)"
