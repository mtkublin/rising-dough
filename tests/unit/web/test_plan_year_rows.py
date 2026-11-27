"""Plan year rows: budgeted rows, every unbudgeted category in the disclosure (T-UR75)."""

from __future__ import annotations

from budget_planner.domain.enums import Direction
from budget_planner.services.budget import YearlyCell, YearlyRow
from budget_planner.web.plan_year_view import year_page


def _row(category_id: int, name: str, amount: int | None) -> YearlyRow:
    cell = YearlyCell(amount_minor=amount, origin="default" if amount else "unset")
    return YearlyRow(
        category_id=category_id,
        category_name=name,
        category_direction=Direction.EXPENSE,
        category_color=None,
        cells=(cell,) * 12,
        total_minor=(amount or 0) * 12,
    )


def test_budgeted_rows_and_every_unbudgeted_category_in_the_disclosure() -> None:
    rows = (
        _row(1, "Bank fees", None),
        _row(2, "Big purchases", 60_435),
        _row(3, "Fixed costs", None),
        _row(4, "Unused", None),
    )

    page = year_page(rows, 2026, current=(2026, 10), currency="PLN")

    assert [r.category_name for r in page.rows] == ["Big purchases"]
    assert [u.category_name for u in page.unbudgeted] == ["Bank fees", "Fixed costs", "Unused"]
    assert page.unbudgeted_heading == "3 categories without a budget"


def test_cells_carry_the_inline_editor_values() -> None:
    rows = (_row(2, "Big purchases", 60_435), _row(1, "Bank fees", None))
    page = year_page(rows, 2026, current=(2026, 10), currency="PLN")

    november = page.rows[0].cells[10]
    assert november.editor_label == "Big purchases, November budget"
    assert (november.amount_text, november.action, november.year) == (
        "604.35",
        "/budget/rules/2/overrides",
        2026,
    )
    assert len(page.rows) == 1
