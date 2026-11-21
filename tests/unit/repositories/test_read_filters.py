"""T-Q268: repository reads are user-scoped and tombstone-aware (ADR-0019 amendment 2026-11-21)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.enums import Cadence, OverrideState
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories import accounts, audit, recurring, snapshots, users
from budget_planner.repositories._shared import require_owned

USER_ID = 1
OTHER_USER_ID = 2


@pytest.fixture
def other_user(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    return OTHER_USER_ID


def test_audit_reads_are_user_scoped(conn: sqlite3.Connection, other_user: int) -> None:
    mine = accounts.create(conn, USER_ID, NewAccount(name="Mine", currency="PLN"))
    theirs = accounts.create(conn, other_user, NewAccount(name="Theirs", currency="PLN"))

    assert [e.entity_id for e in audit.list_entries(conn, USER_ID, "account", mine.id)] == [mine.id]
    assert audit.list_entries(conn, USER_ID, "account", theirs.id) == []
    assert {e.entity_id for e in audit.recent(conn, user_id=USER_ID)} == {mine.id}
    assert {e.entity_id for e in audit.recent(conn, user_id=other_user)} == {theirs.id}


def test_snapshots_hidden_once_account_is_deleted(
    conn: sqlite3.Connection, account_id: int
) -> None:
    snapshots.create(conn, USER_ID, NewAccountSnapshot(account_id=account_id, balance=10, note=""))
    accounts.soft_delete(conn, USER_ID, account_id)

    assert snapshots.list_for_account(conn, USER_ID, account_id) == []
    with pytest.raises(LookupError):
        snapshots.create(
            conn, USER_ID, NewAccountSnapshot(account_id=account_id, balance=20, note="")
        )


def test_snapshots_of_other_users_account_absent(conn: sqlite3.Connection, other_user: int) -> None:
    theirs = accounts.create(conn, other_user, NewAccount(name="Theirs", currency="PLN"))
    snapshots.create(conn, other_user, NewAccountSnapshot(account_id=theirs.id, balance=5, note=""))
    assert snapshots.list_for_account(conn, USER_ID, theirs.id) == []


def test_overrides_of_deleted_rule_are_hidden_and_rejected(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            account_id=account_id,
            category_id=category_id,
            default_amount=100,
            day_of_month=1,
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
        ),
    )
    override = NewRecurringOverride(
        rule_id=rule.id, occurrence_date=date(2026, 2, 1), state=OverrideState.SKIPPED
    )
    recurring.upsert_override(conn, USER_ID, override)
    recurring.soft_delete_rule(conn, USER_ID, rule.id)

    assert recurring.list_overrides(conn, USER_ID, rule.id) == []
    with pytest.raises(LookupError):
        recurring.upsert_override(conn, USER_ID, override)


def test_require_owned_counts_deleted_parent_unless_told_otherwise(
    conn: sqlite3.Connection, account_id: int
) -> None:
    accounts.soft_delete(conn, USER_ID, account_id)

    require_owned(conn, USER_ID, account_ids=(account_id,))
    with pytest.raises(LookupError):
        require_owned(conn, USER_ID, account_ids=(account_id,), include_deleted=False)


def test_owns_accounts_include_deleted_flag(conn: sqlite3.Connection, account_id: int) -> None:
    accounts.soft_delete(conn, USER_ID, account_id)

    assert users.owns_accounts(conn, USER_ID) is True
    assert users.owns_accounts(conn, USER_ID, include_deleted=False) is False
