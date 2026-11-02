"""Account snapshot repository — append-only."""

from __future__ import annotations

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


def list_for_account(conn: sqlite3.Connection, account_id: int) -> list[AccountSnapshot]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM account_snapshots WHERE account_id = ? "
        "ORDER BY taken_at ASC, id ASC",
        (account_id,),
    ).fetchall()
    return [_row_to_snapshot(r) for r in rows]


def create(conn: sqlite3.Connection, data: NewAccountSnapshot) -> AccountSnapshot:
    def _action(c: sqlite3.Connection) -> tuple[int, AccountSnapshot]:
        cursor = c.execute(
            "INSERT INTO account_snapshots(account_id, balance, note) VALUES (?, ?, ?)",
            (data.account_id, data.balance, data.note),
        )
        new_id = int(cursor.lastrowid or 0)
        row = c.execute(
            f"SELECT {_COLUMNS} FROM account_snapshots WHERE id = ?", (new_id,)
        ).fetchone()
        return new_id, _row_to_snapshot(row)

    return mutate(
        conn,
        entity_type="snapshot",
        operation="create",
        prev=None,
        action=_action,
    )


__all__ = ["create", "list_for_account"]
