"""Unit tests for :func:`services.accounts.list_by_last_use` (F8, T-UR00b).

The new-entry dialog lists accounts most recently used first; its default is the first one.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import accounts as accounts_svc

USER_ID = 1
OTHER_USER_ID = 2


def _account(conn: sqlite3.Connection, name: str, user_id: int = USER_ID) -> int:
    return accounts_repo.create(
        conn, user_id, NewAccount(name=name, currency="PLN", opening_balance=0)
    ).id


def _spend(
    conn: sqlite3.Connection,
    account_id: int,
    day: date,
    *,
    category_id: int,
    user_id: int = USER_ID,
) -> int:
    return transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=day, category_id=category_id, account_id=account_id, amount=100
        ),
    ).id


def _names(conn: sqlite3.Connection) -> list[str]:
    return [a.name for a in accounts_svc.list_by_last_use(conn, USER_ID)]


def test_latest_use_first_never_used_last_by_name(conn: sqlite3.Connection) -> None:
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id
    old, new, idle_b, idle_a = (_account(conn, n) for n in ("Old", "New", "Zed", "Abe"))
    _spend(conn, old, date(2026, 10, 12), category_id=cat)
    _spend(conn, new, date(2026, 10, 30), category_id=cat)

    assert _names(conn) == ["New", "Old", "Abe", "Zed"]
    assert idle_a != idle_b


def test_soft_deleted_transaction_is_no_use(conn: sqlite3.Connection) -> None:
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id
    first, second = _account(conn, "First"), _account(conn, "Second")
    _spend(conn, first, date(2026, 10, 1), category_id=cat)
    gone = _spend(conn, second, date(2026, 10, 30), category_id=cat)
    transactions_repo.soft_delete(conn, USER_ID, gone)

    assert _names(conn) == ["First", "Second"]


def test_reconciliation_is_no_use(conn: sqlite3.Connection) -> None:
    food = categories_repo.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id
    reconcile = categories_repo.find_by_name(conn, USER_ID, "Reconciliation")
    assert reconcile is not None
    used, checked = _account(conn, "Used"), _account(conn, "Checked")
    _spend(conn, used, date(2026, 10, 1), category_id=food)
    _spend(conn, checked, date(2026, 10, 29), category_id=reconcile.id)

    assert _names(conn) == ["Used", "Checked"]


def test_second_users_transactions_do_not_count(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    mine_first, mine_second = _account(conn, "Alpha"), _account(conn, "Beta")
    theirs = _account(conn, "Alpha", user_id=OTHER_USER_ID)
    cat = categories_repo.create(
        conn, OTHER_USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id
    _spend(conn, theirs, date(2026, 10, 30), category_id=cat, user_id=OTHER_USER_ID)

    assert _names(conn) == ["Alpha", "Beta"]
    assert (mine_first, mine_second) != (theirs, theirs)
