"""Account snapshot repository — append-only.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Snapshots carry no ``user_id`` column — they are FK-scoped via
``accounts.user_id`` (ADR-0061 §2). Every function takes ``user_id`` as the
first positional arg after ``conn`` for signature symmetry; the SQL joins
through ``accounts`` so a leaked ``account_id`` for a different user filters
out. The ``tests/architecture/test_user_id_filter.py`` static test backstops
the rule.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from budget_planner.domain.snapshots import AccountSnapshot, NewAccountSnapshot
from budget_planner.repositories._shared import mutate, parse_dt_required

_COLUMNS = "id, account_id, taken_at, balance, note"


def _row_to_snapshot(row: sqlite3.Row) -> AccountSnapshot:
    return AccountSnapshot(
        id=row["id"],
        account_id=row["account_id"],
        taken_at=parse_dt_required(row["taken_at"]),
        balance=row["balance"],
        note=row["note"],
    )


def list_for_account(
    conn: sqlite3.Connection, user_id: int, account_id: int
) -> list[AccountSnapshot]:
    cols = ", ".join(f"s.{c}" for c in _COLUMNS.split(", "))
    rows = conn.execute(
        f"SELECT {cols} FROM account_snapshots s "
        "JOIN accounts a ON a.id = s.account_id "
        "WHERE s.account_id = ? AND a.user_id = ? AND a.deleted_at IS NULL "
        "ORDER BY s.taken_at ASC, s.id ASC",
        (account_id, user_id),
    ).fetchall()
    return [_row_to_snapshot(r) for r in rows]


def create(conn: sqlite3.Connection, user_id: int, data: NewAccountSnapshot) -> AccountSnapshot:
    def _action(c: sqlite3.Connection) -> tuple[int, AccountSnapshot]:
        # Validate FK-ownership first; the account must belong to user_id.
        parent = c.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (data.account_id, user_id),
        ).fetchone()
        if parent is None:
            raise LookupError(f"account {data.account_id} not owned by user {user_id}")
        cursor = c.execute(
            "INSERT INTO account_snapshots(account_id, balance, note) VALUES (?, ?, ?)",
            (data.account_id, data.balance, data.note),
        )
        new_id = int(cursor.lastrowid or 0)
        cols = ", ".join(f"s.{c}" for c in _COLUMNS.split(", "))
        row = c.execute(
            f"SELECT {cols} FROM account_snapshots s "
            "JOIN accounts a ON a.id = s.account_id "
            "WHERE s.id = ? AND a.user_id = ? AND a.deleted_at IS NULL",
            (new_id, user_id),
        ).fetchone()
        return new_id, _row_to_snapshot(row)

    return mutate(
        conn,
        entity_type="snapshot",
        operation="create",
        prev=None,
        action=_action,
        user_id=user_id,
    )


def list_for_user(conn: sqlite3.Connection, user_id: int) -> dict[int, list[AccountSnapshot]]:
    """All live accounts' snapshots in one query, grouped by ``account_id`` (T-Q234)."""
    cols = ", ".join(f"s.{c}" for c in _COLUMNS.split(", "))
    rows = conn.execute(
        f"SELECT {cols} FROM account_snapshots s "
        "JOIN accounts a ON a.id = s.account_id "
        "WHERE a.user_id = ? AND a.deleted_at IS NULL "
        "ORDER BY s.taken_at ASC, s.id ASC",
        (user_id,),
    ).fetchall()
    out: dict[int, list[AccountSnapshot]] = {}
    for row in rows:
        snap = _row_to_snapshot(row)
        out.setdefault(snap.account_id, []).append(snap)
    return out


__all__ = ["create", "list_for_account", "list_for_user"]


def latest_taken_at_by_account(conn: sqlite3.Connection, user_id: int) -> dict[int, dt.datetime]:
    """Return ``{account_id: max(taken_at)}`` for the user's live (non-deleted) accounts.

    Snapshots have no ``deleted_at`` of their own; liveness comes from the
    owning account (soft-delete rule, ADR-0022).
    """
    rows = conn.execute(
        """
        SELECT s.account_id AS account_id, MAX(s.taken_at) AS taken_at
        FROM account_snapshots s
        JOIN accounts a ON a.id = s.account_id
        WHERE a.user_id = ? AND a.deleted_at IS NULL
        GROUP BY s.account_id
        """,
        (user_id,),
    ).fetchall()
    return {
        row["account_id"]: dt.datetime.fromisoformat(row["taken_at"].replace("Z", "+00:00"))
        for row in rows
        if row["taken_at"] is not None
    }
