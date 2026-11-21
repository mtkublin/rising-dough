"""Unit tests for :func:`services.accounts.archive_account` (T-Q230, Q-026, ADR-0019)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.errors import ConflictError
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import accounts as accounts_svc

USER_ID = 1
DAY = date(2026, 11, 10)


def _audit_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def _account(
    conn: sqlite3.Connection, opening: int = 0, user_id: int = USER_ID, name: str = "Main"
) -> int:
    return accounts_repo.create(
        conn, user_id, NewAccount(name=name, currency="PLN", opening_balance=opening)
    ).id


def _category(conn: sqlite3.Connection) -> int:
    return categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id


def _live(conn: sqlite3.Connection, account_id: int) -> bool:
    return accounts_repo.find_by_id(conn, USER_ID, account_id) is not None


def test_archive_succeeds_at_zero_balance_without_references(conn: sqlite3.Connection) -> None:
    acc = _account(conn)
    before = _audit_count(conn)

    accounts_svc.archive_account(conn, USER_ID, acc)

    assert not _live(conn, acc)
    assert _audit_count(conn) == before + 1
    row = conn.execute(
        "SELECT entity_type, operation, entity_id FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (row["entity_type"], row["operation"], row["entity_id"]) == ("account", "delete", acc)


def test_archive_refused_when_balance_not_zero(conn: sqlite3.Connection) -> None:
    acc = _account(conn, opening=12_345)
    before = _audit_count(conn)

    with pytest.raises(ConflictError) as err:
        accounts_svc.archive_account(conn, USER_ID, acc)

    assert err.value.message == "Cannot archive account: Balance is not zero"
    assert _live(conn, acc)
    assert _audit_count(conn) == before


def test_archive_allowed_when_transactions_bring_balance_to_zero(
    conn: sqlite3.Connection,
) -> None:
    acc = _account(conn, opening=1_000)
    cat = _category(conn)
    transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(operation_date=DAY, category_id=cat, account_id=acc, amount=1_000),
    )

    accounts_svc.archive_account(conn, USER_ID, acc)

    assert not _live(conn, acc)


def test_archive_refused_by_live_recurring_rules(conn: sqlite3.Connection) -> None:
    acc = _account(conn)
    other = _account(conn, name="Other")
    cat = _category(conn)
    for src, dst in ((acc, None), (other, acc)):
        recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=DAY,
                category_id=cat,
                account_id=src,
                dest_account_id=dst,
                default_amount=500,
            ),
        )
    before = _audit_count(conn)

    with pytest.raises(ConflictError) as err:
        accounts_svc.archive_account(conn, USER_ID, acc)

    assert err.value.message == "Cannot archive account: 2 recurring rules use this account"
    assert _live(conn, acc)
    assert _audit_count(conn) == before


def test_archive_refused_by_unpromoted_planned_row(conn: sqlite3.Connection) -> None:
    acc = _account(conn)
    cat = _category(conn)
    planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(operation_date=DAY, category_id=cat, account_id=acc, amount=700),
    )
    before = _audit_count(conn)

    with pytest.raises(ConflictError) as err:
        accounts_svc.archive_account(conn, USER_ID, acc)

    assert err.value.message == "Cannot archive account: 1 planned transaction uses this account"
    assert _live(conn, acc)
    assert _audit_count(conn) == before


def test_archive_refusal_names_every_blocker(conn: sqlite3.Connection) -> None:
    acc = _account(conn, opening=50)
    cat = _category(conn)
    planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(operation_date=DAY, category_id=cat, account_id=acc, amount=700),
    )

    with pytest.raises(ConflictError) as err:
        accounts_svc.archive_account(conn, USER_ID, acc)

    assert err.value.message == (
        "Cannot archive account: Balance is not zero; 1 planned transaction uses this account"
    )


def test_archive_ignores_inactive_rules_and_deleted_planned_rows(
    conn: sqlite3.Connection,
) -> None:
    acc = _account(conn)
    cat = _category(conn)
    recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=DAY,
            category_id=cat,
            account_id=acc,
            default_amount=500,
            active=False,
        ),
    )
    planned = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(operation_date=DAY, category_id=cat, account_id=acc, amount=700),
    )
    planned_repo.soft_delete(conn, USER_ID, planned.id)

    accounts_svc.archive_account(conn, USER_ID, acc)

    assert not _live(conn, acc)


def test_archive_other_users_account_is_untouched(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    theirs = _account(conn, opening=0, user_id=2)
    before = _audit_count(conn)

    accounts_svc.archive_account(conn, USER_ID, theirs)

    assert accounts_repo.find_by_id(conn, 2, theirs) is not None
    assert _audit_count(conn) == before
