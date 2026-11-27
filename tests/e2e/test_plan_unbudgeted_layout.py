"""E2E: the "without a budget" list on Plan/budget lays out like the main table (T-UR75, T-UR80).

At 375 each row is a card: the category chip keeps its shape, the "no budget" text and the "set
budget" button do not overlap and nothing leaves the card. At 1440 the STATUS column of the list
starts where the main table's does.
"""

from __future__ import annotations

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

# Boxes of the "no budget" text node and of the button of a status cell.
_PARTS_JS = """(cell) => {
  const box = (r) => ({x: r.x, y: r.y, w: r.width, h: r.height});
  const range = document.createRange();
  const text = [...cell.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
  range.selectNodeContents(text);
  const button = cell.querySelector('button');
  return {text: box(range.getBoundingClientRect()), button: box(button.getBoundingClientRect())};
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


def _disjoint(a: dict[str, float], b: dict[str, float]) -> bool:
    return (
        a["x"] + a["w"] <= b["x"] + 0.5
        or b["x"] + b["w"] <= a["x"] + 0.5
        or a["y"] + a["h"] <= b["y"] + 0.5
        or b["y"] + b["h"] <= a["y"] + 0.5
    )


def test_phone_card_keeps_the_chip_and_separates_status_text_from_button(
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
    parts: Any = to_playwright(page, plan_budget.unbudgeted_status_cell(_LISTED)).evaluate(
        _PARTS_JS
    )
    assert _disjoint(parts["text"], parts["button"])
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
