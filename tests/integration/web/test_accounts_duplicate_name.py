"""A live account name is unique per user: create and rename answer 422 on name (T-UR67, F2.1b)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from tests.ui_map import _html, accounts

USER_ID = 1
_DUPLICATE = "▲ An account with this name already exists"


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _account(db: sqlite3.Connection, name: str, user_id: int = USER_ID) -> int:
    return accounts_repo.create(db, user_id, NewAccount(name=name, currency="PLN")).id


def _state(db: sqlite3.Connection) -> tuple[list[str], int]:
    db.commit()  # end any read snapshot so the app's writes are visible
    names = [r[0] for r in db.execute("SELECT name FROM accounts ORDER BY id")]
    return names, int(db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def test_create_with_an_existing_name_is_422_under_the_name_field(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _account(db, "Main")
    before = _state(db)
    r = client.post("/accounts", data={"name": "Main", "currency": "PLN", "opening_balance": "0"})
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text)["field-name-error"] == _DUPLICATE
    assert _html.resolve_one(r.text, accounts.form_name)["value"] == "Main"
    assert _state(db) == before


def test_rename_onto_another_accounts_name_is_422_and_changes_nothing(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _account(db, "Main")
    other = _account(db, "Savings")
    before = _state(db)
    r = client.post(f"/accounts/{other}", data={"name": "Main"})
    assert r.status_code == 422
    assert _html.error_lines(r.text)["field-name-error"] == _DUPLICATE
    assert _state(db) == before


def test_resaving_the_own_name_is_not_a_duplicate(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Main")
    assert client.post(f"/accounts/{acc}", data={"name": "Main"}).status_code == 200


def test_another_users_same_name_does_not_block_create(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    db.commit()
    _account(db, "Main", user_id=2)
    r = client.post("/accounts", data={"name": "Main", "currency": "PLN", "opening_balance": "0"})
    assert r.status_code == 200
    assert [a.name for a in accounts_repo.list_all(db, USER_ID)] == ["Main"]
    assert [a.name for a in accounts_repo.list_all(db, 2)] == ["Main"]
