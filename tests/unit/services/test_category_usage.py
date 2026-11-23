"""T-UR34g (ADR-0147, ADR-0148): category entry counts and picker summary."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import categories as categories_svc

USER_ID = 1
OTHER_USER_ID = 2


def _cat(conn: sqlite3.Connection, name: str, user_id: int = USER_ID) -> int:
    return categories_repo.create(
        conn, user_id, NewCategory(name=name, direction=Direction.EXPENSE)
    ).id


def _account(conn: sqlite3.Connection, user_id: int = USER_ID) -> int:
    return accounts_repo.create(conn, user_id, NewAccount(name="Main", currency="PLN")).id


def _txn(conn: sqlite3.Connection, cat: int, acc: int, day: date, user_id: int = USER_ID) -> int:
    return transactions_repo.create(
        conn,
        user_id,
        NewTransaction(operation_date=day, category_id=cat, account_id=acc, amount=100),
    ).id


@pytest.fixture
def acc(conn: sqlite3.Connection) -> int:
    return _account(conn)


def test_entry_count_counts_live_only(conn: sqlite3.Connection, acc: int) -> None:
    cat = _cat(conn, "Groceries")
    ids = [_txn(conn, cat, acc, date(2026, 10, d)) for d in (1, 2, 3, 4)]
    transactions_repo.soft_delete(conn, USER_ID, ids[3])

    assert categories_svc.entry_count(conn, USER_ID, cat) == 3
    assert categories_svc.entry_count(conn, USER_ID, _cat(conn, "Unused")) == 0


def test_entry_count_ignores_second_user(conn: sqlite3.Connection, acc: int) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    cat = _cat(conn, "Groceries")
    _txn(conn, cat, acc, date(2026, 10, 1))
    other_cat = _cat(conn, "Theirs", OTHER_USER_ID)
    other_acc = _account(conn, OTHER_USER_ID)
    _txn(conn, other_cat, other_acc, date(2026, 10, 9), OTHER_USER_ID)

    assert categories_svc.entry_count(conn, USER_ID, cat) == 1
    assert categories_svc.entry_count(conn, USER_ID, other_cat) == 0
    assert set(categories_svc.usage_by_category(conn, USER_ID)) == {cat}


def test_picker_recent_order_and_ties(conn: sqlite3.Connection, acc: int) -> None:
    a, b, c, d, e = (_cat(conn, n) for n in ("A", "B", "C", "D", "E"))
    _txn(conn, a, acc, date(2026, 10, 1))
    _txn(conn, b, acc, date(2026, 10, 20))
    _txn(conn, b, acc, date(2026, 10, 2))
    _txn(conn, c, acc, date(2026, 10, 20))  # tie with b: lower id first
    _txn(conn, d, acc, date(2026, 10, 10))
    _txn(conn, e, acc, date(2026, 9, 1))

    picker = categories_svc.picker_summary(conn, USER_ID)

    assert [x.id for x in picker.recent] == [b, c, d, a]
    assert len(picker.recent) == categories_svc.RECENT_CATEGORY_LIMIT == 4


def test_picker_excludes_archived_and_deleted_only_usage(
    conn: sqlite3.Connection, acc: int
) -> None:
    live = _cat(conn, "Live")
    archived = _cat(conn, "Archived")
    gone = _cat(conn, "Gone")
    before = categories_svc.picker_summary(conn, USER_ID).total_count
    _txn(conn, live, acc, date(2026, 10, 1))
    _txn(conn, archived, acc, date(2026, 10, 5))
    transactions_repo.soft_delete(conn, USER_ID, _txn(conn, gone, acc, date(2026, 10, 9)))
    categories_svc.archive(conn, USER_ID, archived)

    picker = categories_svc.picker_summary(conn, USER_ID)

    assert [x.id for x in picker.recent] == [live]
    assert picker.total_count == before - 1
    assert picker.total_count == len(categories_repo.list_all(conn, USER_ID))


def test_picker_never_recommends_reconciliation(conn: sqlite3.Connection, acc: int) -> None:
    recon = categories_repo.find_by_name(conn, USER_ID, RECONCILIATION_CATEGORY_NAME)
    assert recon is not None
    _txn(conn, recon.id, acc, date(2026, 10, 30))

    assert recon.id not in [x.id for x in categories_svc.picker_summary(conn, USER_ID).recent]
