"""Tests for the canonical audit helper (T-028)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import pytest

from budget_planner.repositories import audit as audit_repo
from budget_planner.repositories._shared import transaction
from budget_planner.services import audit as audit_service
from budget_planner.services.audit import AuditShapeError


def test_create_sets_prev_null(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        audit_service.write_audit(
            conn,
            entity_type="transaction",
            entity_id=1,
            operation="create",
            prev=None,
            new={"a": 1},
            user_id=None,
        )
    rows = audit_repo.list_entries(conn, "transaction", 1)
    assert len(rows) == 1
    assert rows[0].prev_json is None
    assert json.loads(rows[0].new_json or "{}") == {"a": 1}


def test_update_populates_both(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        audit_service.write_audit(
            conn,
            entity_type="account",
            entity_id=2,
            operation="update",
            prev={"name": "old"},
            new={"name": "new"},
            user_id=None,
        )
    rows = audit_repo.list_entries(conn, "account", 2)
    assert rows[0].prev_json is not None
    assert rows[0].new_json is not None


def test_delete_sets_new_null(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        audit_service.write_audit(
            conn,
            entity_type="account",
            entity_id=3,
            operation="delete",
            prev={"name": "gone"},
            new=None,
            user_id=None,
        )
    rows = audit_repo.list_entries(conn, "account", 3)
    assert rows[0].new_json is None
    assert rows[0].prev_json is not None


def test_undelete_sets_prev_null(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        audit_service.write_audit(
            conn,
            entity_type="account",
            entity_id=4,
            operation="undelete",
            prev=None,
            new={"name": "restored"},
            user_id=None,
        )
    rows = audit_repo.list_entries(conn, "account", 4)
    assert rows[0].prev_json is None
    assert rows[0].new_json is not None


@pytest.mark.parametrize(
    ("operation", "prev", "new"),
    [
        ("create", {"a": 1}, {"a": 2}),  # prev must be None
        ("create", None, None),  # new must not be None
        ("update", {"a": 1}, None),  # new must not be None
        ("update", None, {"a": 1}),  # prev must not be None
        ("delete", None, None),  # prev must not be None
        ("delete", {"a": 1}, {"a": 1}),  # new must be None
        ("undelete", {"a": 1}, {"a": 1}),  # prev must be None
        ("undelete", None, None),  # new must not be None
    ],
)
def test_shape_violations_raise(
    conn: sqlite3.Connection,
    operation: str,
    prev: dict[str, int] | None,
    new: dict[str, int] | None,
) -> None:
    with pytest.raises(AuditShapeError):
        audit_service.write_audit(
            conn,
            entity_type="x",
            entity_id=1,
            operation=operation,  # type: ignore[arg-type]
            prev=prev,
            new=new,
            user_id=None,
        )


def test_unknown_operation_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(AuditShapeError):
        audit_service.write_audit(
            conn,
            entity_type="x",
            entity_id=1,
            operation="purge",  # type: ignore[arg-type]
            prev=None,
            new={"a": 1},
            user_id=None,
        )


def test_dataclass_prev_serialised(conn: sqlite3.Connection) -> None:
    @dataclass(frozen=True)
    class _D:
        name: str

    with transaction(conn):
        audit_service.write_audit(
            conn,
            entity_type="x",
            entity_id=1,
            operation="create",
            prev=None,
            new=_D(name="z"),
            user_id=None,
        )
    row = audit_repo.list_entries(conn, "x", 1)[0]
    assert json.loads(row.new_json or "{}") == {"name": "z"}


def test_rollback_leaves_no_audit_row(conn: sqlite3.Connection) -> None:
    try:
        with transaction(conn):
            audit_service.write_audit(
                conn,
                entity_type="x",
                entity_id=99,
                operation="create",
                prev=None,
                new={"a": 1},
                user_id=None,
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert audit_repo.list_entries(conn, "x", 99) == []
