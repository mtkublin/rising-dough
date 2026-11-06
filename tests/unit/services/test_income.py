"""Tests for `services.income.next_anchor_date` (T-119, ADR-0038)."""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts,
    categories,
    planned,
    recurring,
    transactions,
)
from budget_planner.services import income as income_svc

USER_ID = 1


@pytest.fixture
def ids(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    other = categories.create(
        conn, USER_ID, NewCategory(name="Side", direction=Direction.INCOME)
    ).id
    return {"checking": checking, "salary": salary, "other": other}


# ---------------------------------------------------------------------------
# empty / none
# ---------------------------------------------------------------------------
def test_returns_none_when_empty(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    assert income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 1)) is None


def test_rejects_non_positive_horizon(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        income_svc.next_anchor_date(
            conn, USER_ID, ids["salary"], dt.date(2026, 1, 1), horizon_days=0
        )


# ---------------------------------------------------------------------------
# planned-only
# ---------------------------------------------------------------------------
def test_planned_only_hit(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 2, 5),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 2, 5)


def test_strict_after(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    """``after`` is strict — a row ON the ``after`` date must not match."""
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 1, 20),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 1, 21),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 1, 21)


def test_horizon_limits_search(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 6, 1),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    assert (
        income_svc.next_anchor_date(
            conn, USER_ID, ids["salary"], dt.date(2026, 1, 1), horizon_days=30
        )
        is None
    )
    assert income_svc.next_anchor_date(
        conn, USER_ID, ids["salary"], dt.date(2026, 1, 1), horizon_days=200
    ) == dt.date(2026, 6, 1)


def test_promoted_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    row = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 2, 5),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=dt.date(2026, 2, 5),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=500_000,
            description="",
            promoted_from_planned_id=row.id,
        ),
    )
    planned.stamp_promotion(conn, USER_ID, row.id, txn.id)
    assert income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20)) is None


def test_unknown_category(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 2, 5),
            category_id=ids["other"],
            account_id=ids["checking"],
            amount=500_000,
        ),
    )
    assert income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20)) is None


# ---------------------------------------------------------------------------
# recurring-only
# ---------------------------------------------------------------------------
def test_recurring_only_hit(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 1, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    # Pin next_due into the test's logical window; the repository's
    # ``_compute_initial_next_due`` would otherwise anchor to real today.
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 1, 25)))
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 1, 25)


def test_inactive_rule_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 1, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 1, 25)))
    recurring.deactivate_rule(conn, USER_ID, rule.id)
    assert income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20)) is None


# ---------------------------------------------------------------------------
# both candidates
# ---------------------------------------------------------------------------
def test_both_candidates_recurring_earlier(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 1, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 1, 25)))
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 2, 10),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=100_000,
        ),
    )
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 1, 25)


def test_both_candidates_planned_earlier(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 2, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 2, 25)))
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 2, 1),
            category_id=ids["salary"],
            account_id=ids["checking"],
            amount=100_000,
        ),
    )
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 2, 1)


# ---------------------------------------------------------------------------
# override on recurring next_due
# ---------------------------------------------------------------------------
def test_override_date_moves_recurring(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 1, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 1, 25)))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 1, 25),
            state=OverrideState.OVERRIDDEN,
            date_override=dt.date(2026, 1, 28),
        ),
    )
    result = income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20))
    assert result == dt.date(2026, 1, 28)


def test_override_skipped_excludes_recurring(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 1, 25),
            category_id=ids["salary"],
            account_id=ids["checking"],
            default_amount=500_000,
            default_description="payroll",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=dt.date(2026, 1, 25)))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 1, 25),
            state=OverrideState.SKIPPED,
        ),
    )
    assert income_svc.next_anchor_date(conn, USER_ID, ids["salary"], dt.date(2026, 1, 20)) is None
