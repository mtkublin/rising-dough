"""Every ``plan_year`` name resolves in the handoff year page and overrides (T-UR11, ADR-0106)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, plan_budget, plan_year, rd_fragments
from tests.ui_map.locator import Locator
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page

PAGE = (HANDOFF_ROOT / "pages" / "plan" / "year.html").read_text(encoding="utf-8")
_OVERLAYS = HANDOFF_ROOT / "pages" / "overlays"
MONTH = (_OVERLAYS / "override--budget-month.html").read_text(encoding="utf-8")
EVERY = (_OVERLAYS / "override--budget-every.html").read_text(encoding="utf-8")
DEFAULT = (_OVERLAYS / "override--budget-default.html").read_text(encoding="utf-8")
REMOVE = (_OVERLAYS / "override--remove.html").read_text(encoding="utf-8")
_SAMPLE = "Big Purchases"  # a budgeted sample row of the handoff

_PAGE: dict[str, Locator] = {
    "hero": plan_year.hero,
    "heading": plan_year.heading,
    "panel": plan_year.panel,
    "table_region": plan_year.table_region,
    "table": plan_year.table,
    "rows": plan_year.rows,
    "column_headers": plan_year.column_headers,
    "month_headers": plan_year.month_headers,
    "current_month_header": plan_year.current_month_header,
    "cells": plan_year.cells,
    "row": plan_year.row(_SAMPLE),
    "row_cells": plan_year.row_cells(_SAMPLE),
    "cell": plan_year.cell(_SAMPLE, "January"),
    "disclosure": plan_year.disclosure,
    "tab": plan_budget.tab("budget"),
    "period_nav": rd_fragments.period_nav,
    "period_label": plan_year.period_label,
    "period_prev": plan_year.period_prev,
    "period_next": plan_year.period_next,
    "picker_years": plan_year.picker_years,
}


@pytest.mark.parametrize("name", sorted(_PAGE))
def test_name_resolves_in_handoff_page(name: str) -> None:
    assert _html.count(PAGE, _PAGE[name]) >= 1, name


def test_handoff_page_has_twelve_cells_per_row_and_one_row_per_category() -> None:
    assert _html.count(PAGE, plan_year.row_cells(_SAMPLE)) == 12
    assert _html.count(PAGE, plan_year.row(_SAMPLE)) == 1
    assert _html.count(PAGE, plan_year.month_headers) == 12


@pytest.mark.parametrize(
    ("source", "checked"),
    [
        (MONTH, "this month only"),
        (EVERY, "every october"),
        (DEFAULT, "new default"),
    ],
)
def test_override_dialog_names_resolve_in_handoff(source: str, checked: str) -> None:
    dlg = plan_year.handoff_dialog(_SAMPLE, "Oct 2026")
    assert _html.count(source, dlg) == 1
    for text in ("this month only", "every october", "new default"):
        assert _html.count(source, plan_year.tier(dlg, text)) == 1, text
    assert _html.resolve_one(source, plan_year.tier(dlg, checked)).has_attr("checked")
    assert _html.count(source, plan_year.amount(dlg)) == 1
    assert _html.count(source, plan_year.save(dlg)) == 1
    assert _html.count(source, plan_year.cancel(dlg)) == 1


def test_remove_dialog_names_resolve_in_handoff() -> None:
    dlg = plan_year.remove_dialog()
    assert _html.count(REMOVE, dlg) == 1
    assert _html.count(REMOVE, plan_year.confirm_remove(dlg)) == 1
    assert _html.count(REMOVE, plan_year.keep(dlg)) == 1


def test_year_routes_map_to_the_year_page() -> None:
    assert handoff_page("/plan?tab=year") == "pages/plan/year.html"
