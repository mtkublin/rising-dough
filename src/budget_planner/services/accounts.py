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

from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
)


@dataclass(frozen=True, slots=True)
class LastCheckedRow:
    """One row per live account: id + last-checked timestamp (nullable)."""

    account_id: int
    account_name: str
    last_checked_at: dt.datetime | None
    source: str  # "snapshot" | "reconcile" | "none"


def _latest_snapshot_by_account(conn: sqlite3.Connection) -> dict[int, dt.datetime]:
    """Return ``{account_id: max(taken_at)}`` across non-deleted accounts."""
    rows = conn.execute(
        """
        SELECT account_id, MAX(taken_at) AS taken_at
        FROM account_snapshots
        GROUP BY account_id
        """
    ).fetchall()
    out: dict[int, dt.datetime] = {}
    for row in rows:
        if row["taken_at"] is None:
            continue
        out[row["account_id"]] = dt.datetime.fromisoformat(row["taken_at"].replace("Z", "+00:00"))
    return out


def _latest_reconcile_by_account(
    conn: sqlite3.Connection,
) -> dict[int, dt.date]:
    """Return ``{account_id: max(operation_date)}`` across reconcile txns.

    The reconcile category is seeded with direction=``adjustment``; we match
    by name because the system flag protects it from rename and the join
    stays single-condition. Soft-deleted transactions are excluded.
    """
    cat = categories_repo.find_by_name(conn, RECONCILIATION_CATEGORY_NAME)
    if cat is None:
        return {}
    rows = conn.execute(
        """
        SELECT account_id, MAX(operation_date) AS d
        FROM transactions
        WHERE category_id = ? AND deleted_at IS NULL
        GROUP BY account_id
        """,
        (cat.id,),
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


def last_checked(conn: sqlite3.Connection) -> tuple[LastCheckedRow, ...]:
    """Return one :class:`LastCheckedRow` per live account.

    Ordered by account name (case-insensitive) for deterministic rendering.
    """
    snaps = _latest_snapshot_by_account(conn)
    reconciles = _latest_reconcile_by_account(conn)
    rows: list[LastCheckedRow] = []
    for acc in accounts_repo.list_all(conn):
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


__all__ = ["LastCheckedRow", "last_checked"]
