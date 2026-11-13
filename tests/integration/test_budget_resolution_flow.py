"""Budget three-tier resolution flow (ADR-0014).

Null-coalesces one-off → recurring → default. Zero is a valid distinct
value from None. Spent totals come from actual (not planned) transactions.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.repositories import budgets as budgets_repo
from budget_planner.services import budget as budget_service

USER_ID = 1

pytestmark = pytest.mark.integration


def test_one_off_takes_precedence_in_target_month_only(
    conn: sqlite3.Connection, make_category: Callable[..., int]
) -> None:
    category_id = make_category()
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=10000))
    budgets_repo.set_recurring(
        conn,
        USER_ID,
        NewBudgetRecurringOverride(category_id=category_id, month=12, amount=20000),
    )
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=12, amount=30000),
    )

    # 2026-12: one-off wins.
    assert budget_service.resolve_budget(conn, USER_ID, category_id, 2026, 12) == 30000
    # 2027-12: no one-off → recurring wins.
    assert budget_service.resolve_budget(conn, USER_ID, category_id, 2027, 12) == 20000
    # 2026-11: no override of any kind → default wins.
    assert budget_service.resolve_budget(conn, USER_ID, category_id, 2026, 11) == 10000


def test_resolve_budget_returns_none_when_no_tier_matches(
    conn: sqlite3.Connection, make_category: Callable[..., int]
) -> None:
    category_id = make_category()
    assert budget_service.resolve_budget(conn, USER_ID, category_id, 2026, 5) is None


def test_resolve_budget_zero_is_distinct_from_none(
    conn: sqlite3.Connection, make_category: Callable[..., int]
) -> None:
    category_id = make_category()
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=0))
    assert budget_service.resolve_budget(conn, USER_ID, category_id, 2026, 5) == 0


def test_month_summary_integrates_actual_transactions_only(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_transaction: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    account_id = make_account()
    category_id = make_category(name="Food")
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=50000))

    # Actual spend 120.00
    make_transaction(
        account_id=account_id,
        category_id=category_id,
        amount=12000,
        operation_date=date(2026, 1, 10),
    )
    # Planned 500.00 — must NOT count toward "spent".
    make_planned(
        account_id=account_id,
        category_id=category_id,
        amount=50000,
        operation_date=date(2026, 1, 15),
    )

    summary = budget_service.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 15))
    food_line = next(line for line in summary.lines if line.category_name == "Food")
    assert food_line.budgeted_minor == 50000
    assert food_line.spent_minor == 12000
    assert food_line.remaining_minor == 38000
