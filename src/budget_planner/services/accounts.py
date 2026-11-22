"""Accounts service helpers (T-R42, ADR-0056 §6).

``last_checked`` surfaces the most recent "the user verified this account's
balance" signal: the latest of (a) the newest snapshot's ``taken_at`` and
(b) the newest reconciliation transaction's ``operation_date``. Both are
first-party user actions; derived account activity (regular transactions)
is deliberately excluded.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from budget_planner.domain.accounts import (
    Account,
    NewAccount,
    PatchAccount,
    new_account_errors,
    patch_account_errors,
)
from budget_planner.domain.errors import ConflictError, ValidationError
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.snapshots import AccountSnapshot, NewAccountSnapshot
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    snapshots as snapshots_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services import balance as balance_service


@dataclass(frozen=True, slots=True)
class LastCheckedRow:
    """One row per live account: id + last-checked timestamp (nullable)."""

    account_id: int
    account_name: str
    last_checked_at: dt.datetime | None
    source: str  # "snapshot" | "reconcile" | "none"


def _latest_reconcile_by_account(conn: sqlite3.Connection, user_id: int) -> dict[int, dt.date]:
    """Return ``{account_id: max(operation_date)}`` across live reconcile txns.

    The reconcile category is seeded with direction=``adjustment``; we match
    by name because the system flag protects it from rename. Soft-deleted
    transactions are excluded by the repository.
    """
    cat = categories_repo.find_by_name(conn, user_id, RECONCILIATION_CATEGORY_NAME)
    if cat is None:
        return {}
    return transactions_repo.latest_operation_date_by_account(conn, user_id, cat.id)


def _max_signal(
    snap: dt.datetime | None,
    reconcile_date: dt.date | None,
) -> tuple[dt.datetime | None, str]:
    """Pick the newer signal; return the matching source label."""
    reconcile_dt: dt.datetime | None = None
    if reconcile_date is not None:
        reconcile_dt = dt.datetime(
            reconcile_date.year,
            reconcile_date.month,
            reconcile_date.day,
            tzinfo=dt.UTC,
        )
    if snap is None and reconcile_dt is None:
        return None, "none"
    if snap is None:
        return reconcile_dt, "reconcile"
    if reconcile_dt is None:
        return snap, "snapshot"
    if snap >= reconcile_dt:
        return snap, "snapshot"
    return reconcile_dt, "reconcile"


def last_checked(conn: sqlite3.Connection, user_id: int) -> tuple[LastCheckedRow, ...]:
    """Return one :class:`LastCheckedRow` per live account.

    Ordered by account name (case-insensitive) for deterministic rendering.
    """
    snaps = snapshots_repo.latest_taken_at_by_account(conn, user_id)
    reconciles = _latest_reconcile_by_account(conn, user_id)
    rows: list[LastCheckedRow] = []
    for acc in accounts_repo.list_all(conn, user_id):
        when, source = _max_signal(snaps.get(acc.id), reconciles.get(acc.id))
        rows.append(
            LastCheckedRow(
                account_id=acc.id,
                account_name=acc.name,
                last_checked_at=when,
                source=source,
            )
        )
    rows.sort(key=lambda r: r.account_name.casefold())
    return tuple(rows)


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _archive_blockers(conn: sqlite3.Connection, user_id: int, account_id: int) -> list[str]:
    """Return one message per reason the account cannot be archived (T-Q230)."""
    blockers: list[str] = []
    if balance_service.derive_balance(conn, user_id, account_id) != 0:
        blockers.append("Balance is not zero")
    rules = [
        r
        for r in recurring_repo.list_rules(conn, user_id, active_only=True)
        if account_id in (r.account_id, r.dest_account_id)
    ]
    if rules:
        blockers.append(
            f"{_plural(len(rules), 'recurring rule uses', 'recurring rules use')} this account"
        )
    planned = [
        p
        for p in planned_repo.list_filtered(conn, user_id, PlannedFilter(promoted=False))
        if account_id in (p.account_id, p.dest_account_id)
    ]
    if planned:
        noun = _plural(len(planned), "planned transaction uses", "planned transactions use")
        blockers.append(f"{noun} this account")
    return blockers


def archive_account(conn: sqlite3.Connection, user_id: int, account_id: int) -> None:
    """Soft-delete an account unless balance, rules or planned rows still use it.

    Guard reads and the soft delete share one transaction (ADR-0137). Refusal
    raises :class:`ConflictError` (409) naming every blocker and writes nothing.
    A missing or already-archived account is a no-op.
    """
    with db_transaction(conn):
        if accounts_repo.find_by_id(conn, user_id, account_id) is None:
            return
        blockers = _archive_blockers(conn, user_id, account_id)
        if blockers:
            raise ConflictError(message="Cannot archive account: " + "; ".join(blockers))
        accounts_repo.soft_delete(conn, user_id, account_id)


def find_by_id(
    conn: sqlite3.Connection, user_id: int, account_id: int, *, include_deleted: bool = False
) -> Account | None:
    """The caller's account, or ``None`` (soft-deleted rows only with ``include_deleted``)."""
    return accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=include_deleted)


def find_by_name(
    conn: sqlite3.Connection, user_id: int, name: str, *, include_deleted: bool = False
) -> Account | None:
    """The caller's account with this exact name, or ``None``."""
    return accounts_repo.find_by_name(conn, user_id, name, include_deleted=include_deleted)


def list_all(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> list[Account]:
    """The caller's accounts ordered by name."""
    return accounts_repo.list_all(conn, user_id, include_deleted=include_deleted)


def _raise_if_invalid(errors: dict[str, str]) -> None:
    if errors:
        raise ValidationError(fields=errors)


def create(conn: sqlite3.Connection, user_id: int, data: NewAccount) -> Account:
    """Create an account (one repository mutation: row and audit are atomic).

    Raises :class:`ValidationError` naming each invalid field; writes nothing then.
    """
    _raise_if_invalid(new_account_errors(data))
    return accounts_repo.create(conn, user_id, data)


def update(conn: sqlite3.Connection, user_id: int, account_id: int, data: PatchAccount) -> Account:
    """Patch an account. Raises :class:`ValidationError` for an invalid name or credit limit."""
    _raise_if_invalid(patch_account_errors(data))
    return accounts_repo.update(conn, user_id, account_id, data)


def list_snapshots_for_account(
    conn: sqlite3.Connection, user_id: int, account_id: int
) -> list[AccountSnapshot]:
    """Snapshots of one account, as stored."""
    return snapshots_repo.list_for_account(conn, user_id, account_id)


def list_snapshots_for_user(
    conn: sqlite3.Connection, user_id: int
) -> dict[int, list[AccountSnapshot]]:
    """Snapshots of every account of the user, keyed by account id."""
    return snapshots_repo.list_for_user(conn, user_id)


def create_snapshot(
    conn: sqlite3.Connection, user_id: int, data: NewAccountSnapshot
) -> AccountSnapshot:
    """Record a balance snapshot (one repository mutation)."""
    return snapshots_repo.create(conn, user_id, data)


__all__ = [
    "LastCheckedRow",
    "archive_account",
    "create",
    "create_snapshot",
    "find_by_id",
    "find_by_name",
    "last_checked",
    "list_all",
    "list_snapshots_for_account",
    "list_snapshots_for_user",
    "update",
]
