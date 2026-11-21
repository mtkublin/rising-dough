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

from budget_planner.domain.errors import ConflictError
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    snapshots as snapshots_repo,
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


def _latest_snapshot_by_account(conn: sqlite3.Connection, user_id: int) -> dict[int, dt.datetime]:
    """Return ``{account_id: max(taken_at)}`` across non-deleted accounts."""
    rows = conn.execute(
        """
        SELECT s.account_id AS account_id, MAX(s.taken_at) AS taken_at
        FROM account_snapshots s
        JOIN accounts a ON a.id = s.account_id
        WHERE a.user_id = ?
        GROUP BY s.account_id
        """,
        (user_id,),
    ).fetchall()
    out: dict[int, dt.datetime] = {}
    for row in rows:
        if row["taken_at"] is None:
            continue
        out[row["account_id"]] = dt.datetime.fromisoformat(row["taken_at"].replace("Z", "+00:00"))
    return out


def _latest_reconcile_by_account(conn: sqlite3.Connection, user_id: int) -> dict[int, dt.date]:
    """Return ``{account_id: max(operation_date)}`` across reconcile txns.

    The reconcile category is seeded with direction=``adjustment``; we match
    by name because the system flag protects it from rename and the join
    stays single-condition. Soft-deleted transactions are excluded.
    """
    cat = categories_repo.find_by_name(conn, user_id, RECONCILIATION_CATEGORY_NAME)
    if cat is None:
        return {}
    rows = conn.execute(
        """
        SELECT account_id, MAX(operation_date) AS d
        FROM transactions
        WHERE user_id = ? AND category_id = ? AND deleted_at IS NULL
        GROUP BY account_id
        """,
        (user_id, cat.id),
    ).fetchall()
    out: dict[int, dt.date] = {}
    for row in rows:
        if row["d"] is None:
            continue
        out[row["account_id"]] = dt.date.fromisoformat(row["d"])
    return out


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
    snaps = _latest_snapshot_by_account(conn, user_id)
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


# T-Q241: routers reach persistence only through these service entry points
# (ADR-0142). Plain bindings: behaviour, audit and soft-delete stay in the repository.
find_by_id = accounts_repo.find_by_id
find_by_name = accounts_repo.find_by_name
list_all = accounts_repo.list_all
create = accounts_repo.create
update = accounts_repo.update
list_snapshots_for_account = snapshots_repo.list_for_account
list_snapshots_for_user = snapshots_repo.list_for_user
create_snapshot = snapshots_repo.create


__all__ = ["LastCheckedRow", "archive_account", "last_checked"]
