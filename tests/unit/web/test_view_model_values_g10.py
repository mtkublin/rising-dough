"""T-UR34k (G10): hero fit counts, bar cells, over count, period range, upcoming counts."""

from __future__ import annotations

from datetime import date

import pytest

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.services import budget as budget_service
from budget_planner.services.budget_lines import CategoryBudgetLine
from budget_planner.web import view_models
from budget_planner.web.templating import build_jinja_env
from budget_planner.web.today_data import UpcomingRow

TODAY = date(2026, 10, 31)


@pytest.mark.parametrize(
    ("minor", "ccy", "digits", "marks", "signs"),
    [
        (1_234_567, "PLN", 7, 2, 0),
        (19_999, "PLN", 5, 1, 0),
        (139_993, "PLN", 6, 2, 0),
        (-153_135, "PLN", 6, 2, 1),
        (-1_375_541, "PLN", 7, 2, 1),
        (0, "PLN", 3, 1, 0),
        (1_234_567, "JPY", 7, 2, 0),
    ],
)
def test_hero_fit_counts(minor: int, ccy: str, digits: int, marks: int, signs: int) -> None:
    fit = view_models.hero_fit(minor, ccy)
    assert (fit.digits, fit.marks, fit.signs) == (digits, marks, signs)


def test_hero_fit_filter_registered() -> None:
    env = build_jinja_env(Settings())
    fit = env.filters["hero_fit"](-153_135, "PLN")
    assert (fit.digits, fit.marks, fit.signs) == (6, 2, 1)


@pytest.mark.parametrize(
    ("used", "cells", "min_one", "is_over", "expected"),
    [
        (78, 20, True, False, (16, 4, 22)),
        (39, 10, False, False, (4, 6, 61)),
        (71, 10, False, False, (7, 3, 29)),
        (0, 10, False, False, (0, 10, 100)),
        (3, 20, True, False, (1, 19, 97)),
        (3, 10, False, False, (0, 10, 97)),
        (100, 10, False, False, (10, 0, 0)),
        (50, 10, False, True, (10, 0, 0)),
    ],
)
def test_bar_cells(
    used: int, cells: int, min_one: bool, is_over: bool, expected: tuple[int, int, int]
) -> None:
    bar = view_models.bar_cells(used, cells, is_over=is_over, min_one=min_one)
    assert (bar.filled, bar.empty, bar.left_pct) == expected


def _line(cid: int, budgeted: int, spent: int) -> CategoryBudgetLine:
    return CategoryBudgetLine(
        category_id=cid,
        category_name=f"c{cid}",
        category_direction=Direction.EXPENSE,
        category_color=None,
        budgeted_minor=budgeted,
        spent_minor=spent,
        remaining_minor=budgeted - spent,
        avg_monthly_overall_minor=0,
        avg_this_year_minor=0,
        delta_vs_prev_month_minor=0,
    )


def test_budget_view_over_count_cells_and_period() -> None:
    lines = (
        _line(1, 1000, 1500),
        _line(2, 1000, 390),
        _line(3, 1000, 1001),
        _line(4, 1000, 1000),
        _line(5, 1000, 0),
    )
    summary = budget_service.MonthSummary(
        year=2026,
        month=10,
        lines=lines,
        totals=budget_service.MonthTotals(
            budgeted_minor=5000, spent_minor=3900, committed_minor=0, remaining_minor=1100
        ),
        left_daily_spend_minor=None,
        next_income_date=date(2026, 11, 7),
        days_until_next_income=7,
        anchor_category_name=None,
        period_start=date(2026, 10, 7),
    )
    view = view_models.budget_view(summary, TODAY)
    assert view.over_count == 2
    assert view.spent_pct == 78
    assert (view.left_pct, view.cells.filled, view.cells.empty) == (22, 16, 4)
    assert (view.period_start, view.period_end) == (date(2026, 10, 7), date(2026, 11, 7))
    row = view.lines[1]
    assert (row.used_pct, row.left_pct, row.cells.filled, row.cells.empty) == (39, 61, 4, 6)
    assert (view.lines[0].left_pct, view.lines[0].cells.filled) == (0, 10)
    assert (view.lines[3].left_pct, view.lines[3].cells.filled) == (0, 10)


def _up(day: date, pid: int) -> UpcomingRow:
    return UpcomingRow(
        operation_date=day,
        description="x",
        amount_minor=100,
        is_overdue=day < TODAY,
        kind="planned",
        planned_id=pid,
        rule_id=None,
        override_present=False,
        is_formula=False,
        category_id=1,
        account_id=1,
        dest_account_id=None,
    )


def test_upcoming_group_counts() -> None:
    rows = (
        _up(date(2026, 10, 28), 1),
        _up(date(2026, 10, 31), 2),
        _up(date(2026, 11, 3), 3),
        _up(date(2026, 11, 20), 4),
        _up(date(2026, 11, 25), 5),
    )
    view = view_models.upcoming_view(rows, TODAY, {}, {})
    assert (view.overdue_count, view.due_today_count) == (1, 1)
    assert (view.next_7_count, view.later_count) == (3, 2)
