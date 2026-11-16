"""Tests for `MonthSummary.left_daily_spend_minor` (T-100, ADR-0025, F4.6)."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.repositories import (
    accounts,
    budgets,
    categories,
    planned,
    preferences as preferences_repo,
    recurring,
)
from budget_planner.services import budget as bs, preferences as preferences_svc

USER_ID = 1


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    # 1000.00 budget, no spend → remaining = 100_000 minor.
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=groceries, amount=100_000))
    return {"checking": checking, "groceries": groceries, "salary": salary}


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def test_anchor_set_income_tomorrow(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 16),
            category_id=world["salary"],
            account_id=world["checking"],
            amount=500_000,
        ),
    )
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name == "Salary"
    assert s.next_income_date == date(2026, 2, 16)
    assert s.days_until_next_income == 1
    assert s.left_daily_spend_minor == 100_000


def test_anchor_set_income_in_ten_days(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 25),
            category_id=world["salary"],
            account_id=world["checking"],
            amount=500_000,
        ),
    )
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name == "Salary"
    assert s.days_until_next_income == 10
    assert s.left_daily_spend_minor == 10_000


def test_anchor_set_no_upcoming_falls_back_to_end_of_month(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name is None
    assert s.next_income_date == _end_of_month(2026, 2)
    assert s.left_daily_spend_minor is not None


def test_anchor_unset_falls_back(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name is None
    assert s.next_income_date == _end_of_month(2026, 2)


def test_zero_budget_returns_none(conn: sqlite3.Connection) -> None:
    categories.create(conn, USER_ID, NewCategory(name="X", direction=Direction.EXPENSE))
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.totals.budgeted_minor == 0
    assert s.left_daily_spend_minor is None
    assert s.anchor_category_name is None
    assert s.next_income_date == _end_of_month(2026, 2)
    assert s.days_until_next_income >= 1


def test_today_is_last_day_of_month_denominator_is_one(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=_end_of_month(2026, 2))
    assert s.days_until_next_income == 1
    assert s.left_daily_spend_minor == s.totals.remaining_minor


def test_stale_anchor_falls_back(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    categories.soft_delete(conn, USER_ID, world["salary"])
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name is None
    assert s.next_income_date == _end_of_month(2026, 2)
    # Stale preference row still present.
    assert preferences_repo.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is not None


def test_rounding_half_even(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    # Replace default with 1001 to get remaining = 1001.
    budgets.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=1001)
    )
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 17),
            category_id=world["salary"],
            account_id=world["checking"],
            amount=500_000,
        ),
    )
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.days_until_next_income == 2
    # 1001 / 2 = 500.5 → ROUND_HALF_EVEN picks the even neighbour (500).
    assert s.left_daily_spend_minor == 500


def test_recurring_next_due_hit(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    """T-119: `next_anchor_date` reads `rule.next_due` directly.

    The repository's `_compute_initial_next_due` anchors `next_due` to
    the earliest canonical occurrence on-or-after *actual* ``today``, so
    for a deterministic test we re-point ``next_due`` back to the Feb
    occurrence after the rule is created (ADR-0038 §5 — admin override via
    `PatchRecurringRule`).
    """
    preferences_svc.set_income_anchor_category_id(conn, 1, world["salary"])
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=world["salary"],
            account_id=world["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15))
    assert s.anchor_category_name == "Salary"
    assert s.next_income_date == date(2026, 2, 20)
    assert s.days_until_next_income == 5
    assert s.left_daily_spend_minor == 20_000
