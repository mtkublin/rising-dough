"""T-FIX5 / ADR-0095: budget ``committed`` converts to base currency."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.repositories import (
    accounts,
    budgets,
    categories,
    fx as fx_repo,
    planned,
    preferences as preferences_repo,
    recurring,
)
from budget_planner.services import budget as bs, forecast

USER_ID = 1
TODAY = date(2026, 2, 15)
START = date(2026, 2, 15)
END = date(2026, 2, 25)


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    pln = accounts.create(
        conn, USER_ID, NewAccount(name="PLN", currency="PLN", opening_balance=0)
    ).id
    eur = accounts.create(
        conn, USER_ID, NewAccount(name="EUR", currency="EUR", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    # groceries budgeted, rent unbudgeted.
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=groceries, amount=100_000))
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(salary))
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=END,
            category_id=salary,
            account_id=pln,
            amount=500_000,
        ),
    )
    return {"pln": pln, "eur": eur, "groceries": groceries, "rent": rent, "salary": salary}


def _rate(conn: sqlite3.Connection, on: date, rate: str) -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=on, from_ccy="EUR", to_ccy="PLN", rate=Decimal(rate)))


def _plan(conn: sqlite3.Connection, cat: int, acc: int, amount: int, on: date) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(operation_date=on, category_id=cat, account_id=acc, amount=amount),
    )


def _committed(conn: sqlite3.Connection) -> int:
    return bs.committed_in_window(conn, USER_ID, start=START, end=END, today=TODAY)


def test_planned_eur_converted_with_latest_rate_before_today(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rate(conn, date(2026, 2, 1), "4.00")  # latest on/before today
    _rate(conn, date(2026, 2, 20), "9.99")  # item date: must NOT be used
    _plan(conn, world["groceries"], world["eur"], 12_000, date(2026, 2, 20))
    assert _committed(conn) == 48_000


def test_pln_account_unchanged(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _plan(conn, world["groceries"], world["pln"], 12_000, date(2026, 2, 20))
    assert _committed(conn) == 12_000


def test_recurring_eur_occurrence_converted(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rate(conn, TODAY, "4.30")
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=world["rent"],
            account_id=world["eur"],
            default_amount=10_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))
    assert _committed(conn) == 43_000


def test_month_summary_split_and_remaining_converted(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rate(conn, TODAY, "4.00")
    _plan(conn, world["groceries"], world["eur"], 10_000, date(2026, 2, 20))  # budgeted
    _plan(conn, world["rent"], world["eur"], 5_000, date(2026, 2, 21))  # unbudgeted
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=TODAY)
    assert s.totals.committed_minor == 40_000
    assert s.totals.unbudgeted_committed_minor == 20_000
    assert s.totals.remaining_minor == 100_000 - 40_000
    assert s.left_daily_spend_minor == 6_000  # 60_000 / 10 days


def test_missing_rate_degrades_to_native_amount(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """No cached rate: same graceful degradation as the Today account rows (rate 1)."""
    _plan(conn, world["groceries"], world["eur"], 12_000, date(2026, 2, 20))
    assert _committed(conn) == 12_000


def test_forecast_overlay_committed_converted(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rate(conn, TODAY, "4.00")
    _plan(conn, world["groceries"], world["eur"], 12_000, date(2026, 2, 20))
    got = forecast._committed_future_for_category(
        conn, USER_ID, world["groceries"], date(2026, 2, 16), date(2026, 2, 28), today=TODAY
    )
    assert got == 48_000
