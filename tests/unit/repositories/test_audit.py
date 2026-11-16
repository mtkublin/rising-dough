from __future__ import annotations

import sqlite3

from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts, audit

USER_ID = 1


def test_recent_returns_descending(conn: sqlite3.Connection) -> None:
    a1 = accounts.create(conn, USER_ID, NewAccount(name="A", currency="PLN"))
    a2 = accounts.create(conn, USER_ID, NewAccount(name="B", currency="PLN"))
    rows = audit.recent(conn, limit=10)
    # Newest first.
    assert rows[0].entity_id == a2.id
    assert rows[1].entity_id == a1.id


def test_list_entries_empty(conn: sqlite3.Connection) -> None:
    assert audit.list_entries(conn, "nonexistent", 1) == []
