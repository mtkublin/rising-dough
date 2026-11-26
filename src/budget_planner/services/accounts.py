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
    DUPLICATE_NAME_MESSAGE,
    KIND_FIXED_MESSAGE,
    Account,
    AccountReferences,
    NewAccount,
    PatchAccount,
    new_account_errors,
    patch_account_errors,
)
from budget_planner.domain.errors import AccountInUseError, ValidationError
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


def account_references(
    conn: sqlite3.Connection, user_id: int, account_id: int
) -> AccountReferences:
    """Live transactions (transit legs too), planned rows and recurring rules using the account.

    Soft-deleted rows do not count (T-UR33, F2.8).
    """
    return AccountReferences(
        transactions=transactions_repo.count_referencing_account(conn, user_id, account_id),
        planned=planned_repo.count_referencing_account(conn, user_id, account_id),
        recurring=recurring_repo.count_referencing_account(conn, user_id, account_id),
    )


def _archive_blockers(
    conn: sqlite3.Connection, user_id: int, account_id: int, refs: AccountReferences
) -> list[str]:
    """Return one message per reason the account cannot be archived (T-Q230, T-UR33)."""
    blockers: list[str] = []
    if balance_service.derive_balance(conn, user_id, account_id) != 0:
        blockers.append("Balance is not zero")
    if refs.transactions:
        noun = _plural(refs.transactions, "transaction uses", "transactions use")
        blockers.append(f"{noun} this account")
    if refs.planned:
        noun = _plural(refs.planned, "planned transaction uses", "planned transactions use")
        blockers.append(f"{noun} this account")
    if refs.recurring:
        noun = _plural(refs.recurring, "recurring rule uses", "recurring rules use")
        blockers.append(f"{noun} this account")
    return blockers


def archive_account(conn: sqlite3.Connection, user_id: int, account_id: int) -> None:
    """Soft-delete an account unless balance or live rows still use it.

    Guard reads and the soft delete share one transaction (ADR-0137). Refusal
    raises :class:`AccountInUseError` (a 409 ``ConflictError``) naming every
    blocker and carrying the :class:`AccountReferences` counts; nothing is
    written. A missing or already-archived account is a no-op.
    """
    with db_transaction(conn):
        if accounts_repo.find_by_id(conn, user_id, account_id) is None:
            return
        refs = account_references(conn, user_id, account_id)
        blockers = _archive_blockers(conn, user_id, account_id, refs)
        if blockers:
            raise AccountInUseError(
                "Cannot archive account: " + "; ".join(blockers), references=refs
            )
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


def list_by_last_use(conn: sqlite3.Connection, user_id: int) -> list[Account]:
    """The caller's accounts, most recently used first (never-used last), then by name.

    "Used" is a live transaction that is not a reconciliation; the first account is the
    new-entry dialog's default (T-UR00b, handoff: Credit Card, the latest used, first).
    """
    last = transactions_repo.account_last_used(conn, user_id)
    return sorted(
        accounts_repo.list_all(conn, user_id),
        key=lambda a: (-last[a.id].toordinal() if a.id in last else 0, a.name),
    )


def _raise_if_invalid(errors: dict[str, str]) -> None:
    if errors:
        raise ValidationError(fields=errors)


def _duplicate_name_errors(
    conn: sqlite3.Connection, user_id: int, name: str | None, *, own_id: int | None
) -> dict[str, str]:
    """A name error when another live account of the user has ``name`` (the unique index)."""
    if name is None:
        return {}
    other = accounts_repo.find_by_name(conn, user_id, name)
    if other is not None and other.id != own_id:
        return {"name": DUPLICATE_NAME_MESSAGE}
    return {}


def create(conn: sqlite3.Connection, user_id: int, data: NewAccount) -> Account:
    """Create an account (one repository mutation: row and audit are atomic).

    Raises :class:`ValidationError` naming each invalid field; writes nothing then.
    """
    errors = new_account_errors(data)
    if "name" not in errors:
        errors = {**errors, **_duplicate_name_errors(conn, user_id, data.name, own_id=None)}
    _raise_if_invalid(errors)
    return accounts_repo.create(conn, user_id, data)


def update(conn: sqlite3.Connection, user_id: int, account_id: int, data: PatchAccount) -> Account:
    """Patch an account.

    Raises :class:`ValidationError` for an invalid name or credit limit, or a changed
    asset/liability kind (fixed at creation; the form is not trusted).
    """
    errors = patch_account_errors(data)
    stored = accounts_repo.find_by_id(conn, user_id, account_id)
    if stored is not None and data.is_liability not in (None, stored.is_liability):
        errors = {**errors, "is_liability": KIND_FIXED_MESSAGE}
    if "name" not in errors:
        errors = {**errors, **_duplicate_name_errors(conn, user_id, data.name, own_id=account_id)}
    _raise_if_invalid(errors)
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
    "list_by_last_use",
    "list_snapshots_for_account",
    "list_snapshots_for_user",
    "update",
]
