from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import pytest

from budget_planner.repositories import audit
from budget_planner.repositories._shared import (
    _dumps,
    mutate,
    parse_dt,
    parse_dt_required,
    transaction,
    utc_now_iso,
    write_audit,
)


def test_utc_now_iso_format() -> None:
    value = utc_now_iso()
    assert value.endswith("Z")
    assert "T" in value


def test_dumps_none() -> None:
    assert _dumps(None) is None


def test_dumps_dict_sorted() -> None:
    payload = _dumps({"b": 2, "a": 1})
    assert payload == '{"a": 1, "b": 2}'


def test_dumps_dataclass() -> None:
    @dataclass(frozen=True)
    class _D:
        name: str
        n: int

    payload = _dumps(_D(name="x", n=5))
    assert json.loads(payload or "{}") == {"n": 5, "name": "x"}


def test_parse_dt_round_trip() -> None:
    assert parse_dt(None) is None
    dt = parse_dt("2026-10-23T10:11:12.345Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_dt_required() -> None:
    dt = parse_dt_required("2026-10-23T10:11:12.345Z")
    assert dt.tzinfo is not None


def test_transaction_rolls_back_on_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError), transaction(conn):
        conn.execute("INSERT INTO users(id, name) VALUES (42, 'x') ON CONFLICT(id) DO NOTHING")
        raise RuntimeError("boom")
    row = conn.execute("SELECT * FROM users WHERE id = 42").fetchone()
    assert row is None


def test_mutate_writes_audit_and_rolls_back_on_failure(
    conn: sqlite3.Connection,
) -> None:
    def _ok(c: sqlite3.Connection) -> tuple[int, dict[str, int]]:
        return 7, {"x": 1}

    mutate(conn, entity_type="test", operation="create", prev=None, action=_ok, user_id=None)
    rows = audit.list_entries(conn, None, "test", 7)
    assert len(rows) == 1
    assert rows[0].operation.value == "create"
    assert json.loads(rows[0].new_json or "{}") == {"x": 1}

    def _bad(c: sqlite3.Connection) -> tuple[int, None]:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        mutate(conn, entity_type="test", operation="update", prev=None, action=_bad, user_id=None)
    assert audit.list_entries(conn, None, "test", 7) == rows


def test_nested_savepoint_rolls_back_inner_only(conn: sqlite3.Connection) -> None:
    """Nested `transaction()` call should ROLLBACK TO savepoint, not the outer txn."""
    with transaction(conn):
        conn.execute("INSERT INTO users(id, name) VALUES (101, 'outer')")
        with pytest.raises(RuntimeError), transaction(conn):
            conn.execute("INSERT INTO users(id, name) VALUES (102, 'inner')")
            raise RuntimeError("inner failed")
        # Outer survived; inner rolled back.
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = 101").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = 102").fetchone()[0] == 0


def test_write_audit_directly(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    try:
        write_audit(
            conn,
            entity_type="t",
            entity_id=1,
            operation="create",
            prev=None,
            new={"name": "a"},
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    rows = audit.list_entries(conn, None, "t", 1)
    assert len(rows) == 1
    assert rows[0].new_json is not None
