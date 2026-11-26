"""The account service refuses a duplicate live name on create and rename (T-UR67)."""

from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.errors import ValidationError
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import accounts as accounts_svc

USER_ID = 1
_FIELDS = {"name": "An account with this name already exists"}


def _audit_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def test_create_refuses_a_live_duplicate_and_writes_nothing(conn: sqlite3.Connection) -> None:
    accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
    before = _audit_count(conn)
    with pytest.raises(ValidationError) as err:
        accounts_svc.create(conn, USER_ID, NewAccount(name="Main", currency="EUR"))
    assert err.value.fields == _FIELDS
    assert _audit_count(conn) == before
    assert len(accounts_repo.list_all(conn, USER_ID)) == 1


def test_update_refuses_a_rename_onto_another_account(conn: sqlite3.Connection) -> None:
    accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
    other = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
    before = _audit_count(conn)
    with pytest.raises(ValidationError) as err:
        accounts_svc.update(conn, USER_ID, other.id, PatchAccount(name="Main"))
    assert err.value.fields == _FIELDS
    assert _audit_count(conn) == before


def test_update_keeping_the_own_name_and_archived_names_are_fine(conn: sqlite3.Connection) -> None:
    old = accounts_repo.create(conn, USER_ID, NewAccount(name="Old", currency="PLN"))
    accounts_repo.soft_delete(conn, USER_ID, old.id)
    fresh = accounts_svc.create(conn, USER_ID, NewAccount(name="Old", currency="PLN"))
    assert accounts_svc.update(conn, USER_ID, fresh.id, PatchAccount(name="Old")).name == "Old"
