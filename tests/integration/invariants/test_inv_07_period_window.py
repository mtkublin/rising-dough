# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-7: period windows agree when no income anchor is configured (Q-003).

``budget._resolve_anchor`` returns the last day of the month as the exclusive end of the committed window and divides
by ``(end - today).days``; ``account_planned.resolve_window`` returns last day + 1. A 5000 expense planned on the last
day is the probe.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import planned as planned_repo
from budget_planner.services import account_planned, budget
from tests.formula_fx_support import formula_fx_of

U = 1
TODAY = date(2026, 11, 19)


def _snapshot(conn: sqlite3.Connection) -> tuple[int, int, int]:
    s = budget.month_summary(conn, U, 2026, 11, today=TODAY, base_currency="PLN")
    win = account_planned.resolve_window(conn, U, TODAY)
    net1 = account_planned.planned_net_by_account(conn, U, win, formula_fx_of(conn, U)).get(1, 0)
    committed = s.totals.committed_minor + s.totals.unbudgeted_committed_minor
    return committed, net1, s.days_until_next_income


def _plan(conn: sqlite3.Connection, day: date) -> None:
    planned_repo.create(
        conn,
        U,
        NewPlannedTransaction(
            operation_date=day, category_id=7, account_id=1, amount=5000, description=str(day)
        ),
    )


@pytest.fixture
def no_anchor(seeded: sqlite3.Connection) -> sqlite3.Connection:
    seeded.execute("DELETE FROM user_preferences WHERE key = 'income_anchor_category_id'")
    return seeded


def test_an_item_before_the_last_day_is_counted_by_both(no_anchor: sqlite3.Connection) -> None:
    b0, n0, _ = _snapshot(no_anchor)
    _plan(no_anchor, date(2026, 11, 29))
    b1, n1, _ = _snapshot(no_anchor)
    assert (b1 - b0, n1 - n0) == (5000, -5000)


def test_an_item_on_the_last_day_is_counted_by_both(no_anchor: sqlite3.Connection) -> None:
    b0, n0, _ = _snapshot(no_anchor)
    _plan(no_anchor, date(2026, 11, 30))
    b1, n1, _ = _snapshot(no_anchor)
    assert (b1 - b0, n1 - n0) == (5000, -5000)


def test_left_per_day_divisor_counts_today_through_month_end(no_anchor: sqlite3.Connection) -> None:
    _, _, days = _snapshot(no_anchor)
    assert days == (date(2026, 11, 30) - TODAY).days + 1
