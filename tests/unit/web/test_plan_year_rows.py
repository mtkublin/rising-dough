"""Plan year rows: budgeted first, then used but unbudgeted, hidden when unused (T-UR00b)."""

from __future__ import annotations

from budget_planner.domain.enums import Direction
from budget_planner.services.budget import YearlyCell, YearlyRow
from budget_planner.services.categories import CategoryUsage
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


def _usage(entries: int, planned: int = 0, rules: int = 0) -> CategoryUsage:
    return CategoryUsage(
        entry_count=entries, planned_count=planned, rule_count=rules, last_used=None
    )


def test_unbudgeted_categories_are_listed_by_use() -> None:
    rows = (
        _row(1, "Bank fees", None),  # a rule only: an unset grid row
        _row(2, "Big purchases", 60_435),
        _row(3, "Fixed costs", None),  # entries: the disclosure
        _row(4, "Taxes", None),  # entries and a rule: the disclosure
        _row(5, "Unused", None),  # nothing uses it: hidden
    )
    usage = {1: _usage(0, rules=1), 3: _usage(7), 4: _usage(2, rules=1)}

    page = year_page(rows, 2026, current=(2026, 10), currency="PLN", usage=usage)

    assert [r.category_name for r in page.rows] == ["Big purchases", "Bank fees"]
    assert [c.text for c in page.rows[1].cells] == ["\N{EN DASH}"] * 12
    assert [u.category_name for u in page.unbudgeted] == ["Fixed costs", "Taxes"]
    assert page.unbudgeted_heading == "2 categories without a budget"
