"""Unit tests for :func:`services.accounts.last_checked` (T-R42, ADR-0056 §6)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories import (
    accounts as accounts_repo,
    snapshots as snapshots_repo,
)
from budget_planner.services import (
    accounts as accounts_svc,
    reconciliation as reconciliation_svc,
)

USER_ID = 1


@pytest.fixture
def two_accounts(conn: sqlite3.Connection) -> tuple[int, int]:
    a = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Alpha", currency="PLN", opening_balance=10_000)
    ).id
    b = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Beta", currency="PLN", opening_balance=5_000)
    ).id
    return a, b


def test_last_checked_empty_accounts_return_none(conn: sqlite3.Connection) -> None:
    rows = accounts_svc.last_checked(conn, USER_ID)
    assert rows == ()


def test_last_checked_no_signal_source_none(
    conn: sqlite3.Connection,
    two_accounts: tuple[int, int],
) -> None:
    rows = accounts_svc.last_checked(conn, USER_ID)
    assert len(rows) == 2
    assert all(r.source == "none" for r in rows)
    assert all(r.last_checked_at is None for r in rows)


def test_last_checked_snapshot_only(
    conn: sqlite3.Connection,
    two_accounts: tuple[int, int],
) -> None:
    a, _ = two_accounts
    snapshots_repo.create(conn, USER_ID, NewAccountSnapshot(account_id=a, balance=10_000, note="x"))
    rows = {r.account_id: r for r in accounts_svc.last_checked(conn, USER_ID)}
    assert rows[a].source == "snapshot"
    assert rows[a].last_checked_at is not None


def test_last_checked_reconcile_only(
    conn: sqlite3.Connection,
    two_accounts: tuple[int, int],
) -> None:
    _, b = two_accounts
    reconciliation_svc.reconcile(conn, USER_ID, b, 20_000, date(2026, 2, 15))
    rows = {r.account_id: r for r in accounts_svc.last_checked(conn, USER_ID)}
    assert rows[b].source == "reconcile"
    when = rows[b].last_checked_at
    assert when is not None
    assert when.date() == date(2026, 2, 15)


def test_last_checked_picks_newer_signal(
    conn: sqlite3.Connection,
    two_accounts: tuple[int, int],
) -> None:
    a, _ = two_accounts
    # Reconcile with a past date; snapshot taken now → snapshot wins.
    reconciliation_svc.reconcile(conn, USER_ID, a, 20_000, date(2020, 1, 1))
    snapshots_repo.create(conn, USER_ID, NewAccountSnapshot(account_id=a, balance=20_000, note="x"))
    rows = {r.account_id: r for r in accounts_svc.last_checked(conn, USER_ID)}
    assert rows[a].source == "snapshot"


def test_last_checked_sorted_by_name(
    conn: sqlite3.Connection,
    two_accounts: tuple[int, int],
) -> None:
    rows = accounts_svc.last_checked(conn, USER_ID)
    names = [r.account_name for r in rows]
    assert names == sorted(names, key=str.casefold)
