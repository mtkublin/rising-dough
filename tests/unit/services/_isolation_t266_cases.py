"""Isolation cases for budget_rules and account_reconcile (T-Q266).

Same world and conventions as ``_isolation_read_cases.py``: one user's calls never show or
change the other user's rows.
"""

from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import transactions as transactions_repo
from budget_planner.services import (
    account_reconcile,
    accounts,
    budget_overrides,
    budget_rules,
    reconciliation,
)
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    WORLD_TODAY,
    World,
    budget_amount,
)


@covers("budget_rules.rules_rows")
def _case_rules_rows(conn: sqlite3.Connection, world: World) -> None:
    owner_rows = budget_rules.rules_rows(conn, OWNER_ID)
    other_rows = budget_rules.rules_rows(conn, OTHER_ID)
    assert [(r.category_id, r.default_minor) for r in owner_rows] == [
        (world.owner.category_id, budget_amount(OWNER_ID))
    ]
    assert [(r.category_id, r.default_minor) for r in other_rows] == [
        (world.other.category_id, budget_amount(OTHER_ID))
    ]


@covers("budget_rules.apply_override")
def _case_apply_override(conn: sqlite3.Connection, world: World) -> None:
    budget_rules.apply_override(
        conn, OWNER_ID, NewBudgetDefault(category_id=world.owner.category_id, amount=777)
    )
    own = budget_overrides.get_default(conn, OWNER_ID, world.owner.category_id)
    assert own is not None
    assert own.amount == 777
    theirs = budget_overrides.get_default(conn, OTHER_ID, world.other.category_id)
    assert theirs is not None
    assert theirs.amount == budget_amount(OTHER_ID)
    assert budget_overrides.get_default(conn, OWNER_ID, world.other.category_id) is None


@covers("account_reconcile.reconcile_account")
def _case_reconcile_account(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(reconciliation.AccountNotFoundError):
        account_reconcile.reconcile_account(
            conn,
            OTHER_ID,
            account_id=world.owner.account_id,
            actual_balance_minor=1,
            today=WORLD_TODAY,
        )
    assert accounts.list_snapshots_for_account(conn, OWNER_ID, world.owner.account_id) == []
    account_reconcile.reconcile_account(
        conn,
        OWNER_ID,
        account_id=world.owner.account_id,
        actual_balance_minor=OWNER_BALANCE,
        today=WORLD_TODAY,
    )
    snaps = accounts.list_snapshots_for_account(conn, OWNER_ID, world.owner.account_id)
    assert [(s.balance, s.note) for s in snaps] == [(OWNER_BALANCE, "reconcile snapshot")]
    assert accounts.list_snapshots_for_account(conn, OTHER_ID, world.other.account_id) == []
    other_txns = transactions_repo.list_filtered(conn, OTHER_ID, TransactionFilter())
    assert [t.amount for t in other_txns] == [2_000]  # user 2's ledger is untouched
