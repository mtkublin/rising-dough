"""Every ``plan_budget`` name resolves in the handoff's budget page (T-UR11, ADR-0106)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, plan_budget
from tests.ui_map.locator import Locator
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page

PAGE = (HANDOFF_ROOT / "pages" / "plan" / "budget.html").read_text(encoding="utf-8")
_SAMPLE = "Groceries"  # a budgeted sample row of the handoff

_STATIC: dict[str, Locator] = {
    "hero": plan_budget.hero,
    "heading": plan_budget.heading,
    "panel": plan_budget.panel,
    "tabs": plan_budget.tabs,
    "table": plan_budget.table,
    "table_region": plan_budget.table_region,
    "rows": plan_budget.rows,
    "total_row": plan_budget.total_row,
    "column_headers": plan_budget.column_headers,
    "tab": plan_budget.tab("year"),
    "row": plan_budget.row(_SAMPLE),
    "row_cells": plan_budget.row_cells(_SAMPLE),
    "bar": plan_budget.bar(_SAMPLE),
    "row_menu_button": plan_budget.row_menu_button(_SAMPLE),
    "row_menu": plan_budget.row_menu(_SAMPLE),
    "override_item": plan_budget.override_item(_SAMPLE),
    "menu_cancel": plan_budget.menu_cancel(_SAMPLE),
}


@pytest.mark.parametrize("name", sorted(_STATIC))
def test_name_resolves_in_handoff(name: str) -> None:
    assert _html.count(PAGE, _STATIC[name]) >= 1, name


def test_handoff_sample_has_one_row_per_category_and_a_total() -> None:
    assert _html.count(PAGE, plan_budget.total_row) == 1
    assert _html.count(PAGE, plan_budget.row(_SAMPLE)) == 1


def test_plan_routes_map_to_the_budget_page() -> None:
    for route in ("/plan", "/plan?tab=budget"):
        assert handoff_page(route) == "pages/plan/budget.html"
