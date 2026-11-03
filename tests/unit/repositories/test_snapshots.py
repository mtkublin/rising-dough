from __future__ import annotations

import sqlite3

from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories import audit, snapshots

USER_ID = 1


def test_create_and_list(conn: sqlite3.Connection, account_id: int) -> None:
    snap = snapshots.create(
        conn, USER_ID, NewAccountSnapshot(account_id=account_id, balance=1000, note="opening")
    )
    assert snap.balance == 1000
    assert snapshots.list_for_account(conn, USER_ID, account_id) == [snap]
    assert audit.list_entries(conn, "snapshot", snap.id)[0].operation.value == "create"
