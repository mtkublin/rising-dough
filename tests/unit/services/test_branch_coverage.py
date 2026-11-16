"""Targeted branch-coverage tests for the service layer.

Closes two residual partial branches:
  * ``services/balance.py:140->142`` — ``last_date`` kept when a same-date
    transaction follows.
  * ``services/planned.py:134`` — ``_match_non_date_filters`` returning
    True when a ``recurring_rule_id`` filter is set and does match.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction, PlannedFilter
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as txn_repo,
)
from budget_planner.services import balance as balance_service, planned as planned_service

USER_ID = 1

pytestmark = pytest.mark.unit


@pytest.fixture
def account_id(conn: sqlite3.Connection) -> int:
    return accounts_repo.create(conn, USER_ID, NewAccount(name="ING", currency="PLN")).id


@pytest.fixture
def category_id(conn: sqlite3.Connection) -> int:
    return categories_repo.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id


def test_account_stats_two_same_date_txns_keeps_first_date_assignment(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """Second same-date transaction skips the ``last_date = txn.operation_date``
    reassignment (closes the 140->142 branch)."""
    txn_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 3, 15),
            category_id=category_id,
            account_id=account_id,
            amount=1000,
        ),
    )
    txn_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 3, 15),
            category_id=category_id,
            account_id=account_id,
            amount=2000,
        ),
    )
    stats = balance_service.account_stats(conn, USER_ID, account_id)
    assert stats.last_txn_date == "2026-03-15"
    assert stats.txn_count == 2


def test_list_planned_promoted_true_filter_keeps_promoted_rows(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """`filters.promoted=True` matching a promoted row closes line 134's final
    branch (view.is_promoted == filters.promoted → return True)."""
    unpromoted = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 10),
            category_id=category_id,
            account_id=account_id,
            amount=1111,
        ),
    )
    promoted = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 20),
            category_id=category_id,
            account_id=account_id,
            amount=2222,
        ),
    )
    txn = txn_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 20),
            category_id=category_id,
            account_id=account_id,
            amount=2222,
            promoted_from_planned_id=promoted.id,
        ),
    )
    planned_repo.stamp_promotion(conn, USER_ID, promoted.id, txn.id)

    result = planned_service.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            promoted=True,
        ),
    )
    kept = {v.persisted_id for v in result}
    assert promoted.id in kept
    assert unpromoted.id not in kept


def test_list_planned_recurring_rule_id_filter_matches_persisted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """`recurring_rule_id` filter returning True through all guards closes
    the final ternary branch in ``_match_non_date_filters``."""
    rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=1000,
        ),
    )
    linked = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            amount=1000,
            recurring_rule_id=rule.id,
            occurrence_date=date(2026, 1, 15),
        ),
    )
    unrelated = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 20),
            category_id=category_id,
            account_id=account_id,
            amount=2000,
        ),
    )

    filtered = planned_service.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            recurring_rule_id=rule.id,
            promoted=False,
        ),
    )
    ids = {v.persisted_id for v in filtered if v.persisted_id is not None}
    assert linked.id in ids
    assert unrelated.id not in ids

    # Filter with a different recurring_rule_id → both persisted rows excluded;
    # closes the ``return False`` branch at services/planned.py:134 (rule mismatch).
    nothing = planned_service.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            recurring_rule_id=rule.id + 999,
            promoted=False,
        ),
    )
    assert nothing == ()
