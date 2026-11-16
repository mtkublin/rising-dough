"""Cross-user isolation at the repository layer (T-D16 / ADR-0061 §5).

User 2's rows must never surface through a user-1-scoped repository call,
and vice versa. Every read, update, and delete path is scoped by
``user_id``; a leaked row id belonging to another user behaves as "not
found".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction, PlannedFilter
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    TransactionFilter,
)
from budget_planner.repositories import accounts, categories, planned, transactions

USER_ID = 1
OTHER_USER_ID = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class _Owned:
    account_id: int
    category_id: int
    txn_id: int
    planned_id: int


def _seed_user(conn: sqlite3.Connection, user_id: int, tag: str) -> _Owned:
    account = accounts.create(conn, user_id, NewAccount(name=f"Bank {tag}", currency="PLN"))
    category = categories.create(
        conn, user_id, NewCategory(name=f"Food {tag}", direction=Direction.EXPENSE)
    )
    txn = transactions.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=date(2026, 3, 1),
            category_id=category.id,
            account_id=account.id,
            amount=1234,
            description=f"txn {tag}",
        ),
    )
    plan = planned.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=date(2026, 4, 1),
            category_id=category.id,
            account_id=account.id,
            amount=500,
        ),
    )
    return _Owned(account_id=account.id, category_id=category.id, txn_id=txn.id, planned_id=plan.id)


@pytest.fixture
def two_users(conn: sqlite3.Connection) -> tuple[_Owned, _Owned]:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    return _seed_user(conn, USER_ID, "one"), _seed_user(conn, OTHER_USER_ID, "two")


def test_accounts_are_isolated(conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]) -> None:
    mine, theirs = two_users
    assert [a.id for a in accounts.list_all(conn, USER_ID)] == [mine.account_id]
    assert [a.id for a in accounts.list_all(conn, OTHER_USER_ID)] == [theirs.account_id]
    assert accounts.find_by_id(conn, USER_ID, theirs.account_id) is None
    assert accounts.find_by_id(conn, OTHER_USER_ID, mine.account_id) is None
    assert accounts.find_by_name(conn, USER_ID, "Bank two") is None


def test_account_update_and_delete_cannot_cross_users(
    conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]
) -> None:
    _, theirs = two_users
    with pytest.raises(LookupError):
        accounts.update(conn, USER_ID, theirs.account_id, PatchAccount(name="hijacked"))
    accounts.soft_delete(conn, USER_ID, theirs.account_id)
    still_there = accounts.find_by_id(conn, OTHER_USER_ID, theirs.account_id)
    assert still_there is not None
    assert still_there.name == "Bank two"
    assert still_there.deleted_at is None


def test_categories_are_isolated(
    conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]
) -> None:
    mine, theirs = two_users
    mine_ids = {c.id for c in categories.list_all(conn, USER_ID)}
    theirs_ids = {c.id for c in categories.list_all(conn, OTHER_USER_ID)}
    assert mine.category_id in mine_ids
    assert theirs.category_id not in mine_ids
    assert theirs_ids == {theirs.category_id}
    assert categories.find_by_id(conn, USER_ID, theirs.category_id) is None
    assert categories.find_by_name(conn, OTHER_USER_ID, "Food one") is None


def test_transactions_are_isolated(
    conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]
) -> None:
    mine, theirs = two_users
    assert [t.id for t in transactions.list_filtered(conn, USER_ID, TransactionFilter())] == [
        mine.txn_id
    ]
    assert [t.id for t in transactions.list_filtered(conn, OTHER_USER_ID, TransactionFilter())] == [
        theirs.txn_id
    ]
    assert transactions.find_by_id(conn, USER_ID, theirs.txn_id) is None
    with pytest.raises(LookupError):
        transactions.update(conn, USER_ID, theirs.txn_id, PatchTransaction(amount=1))
    transactions.soft_delete(conn, USER_ID, theirs.txn_id)
    untouched = transactions.find_by_id(conn, OTHER_USER_ID, theirs.txn_id)
    assert untouched is not None
    assert untouched.amount == 1234


def test_planned_are_isolated(conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]) -> None:
    mine, theirs = two_users
    assert [p.id for p in planned.list_filtered(conn, USER_ID, PlannedFilter())] == [
        mine.planned_id
    ]
    assert [p.id for p in planned.list_filtered(conn, OTHER_USER_ID, PlannedFilter())] == [
        theirs.planned_id
    ]
    assert planned.find_by_id(conn, USER_ID, theirs.planned_id) is None
    planned.soft_delete(conn, USER_ID, theirs.planned_id)
    assert planned.find_by_id(conn, OTHER_USER_ID, theirs.planned_id) is not None


def test_cannot_link_other_users_account_or_category(
    conn: sqlite3.Connection, two_users: tuple[_Owned, _Owned]
) -> None:
    mine, theirs = two_users
    with pytest.raises(LookupError, match="account"):
        transactions.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 3, 2),
                category_id=mine.category_id,
                account_id=theirs.account_id,
                amount=1,
            ),
        )
    with pytest.raises(LookupError, match="category"):
        planned.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 4, 2),
                category_id=theirs.category_id,
                account_id=mine.account_id,
                amount=1,
            ),
        )
    with pytest.raises(LookupError, match="account"):
        transactions.update(
            conn, USER_ID, mine.txn_id, PatchTransaction(dest_account_id=theirs.account_id)
        )
