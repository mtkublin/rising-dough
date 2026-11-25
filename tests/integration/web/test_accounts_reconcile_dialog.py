"""Reconcile dialog on the shared shell: difference hero, preview, available credit (T-UR08b)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from tests.ui_map import _html, accounts, shell

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _asset(db: sqlite3.Connection) -> int:
    new = NewAccount(name="Checking", currency="PLN", opening_balance=10_000)
    return accounts_repo.create(db, USER_ID, new).id


def _visa(db: sqlite3.Connection) -> int:
    new = NewAccount(
        name="Visa",
        currency="PLN",
        opening_balance=-123_456,
        is_liability=True,
        credit_limit_minor=500_000,
    )
    return accounts_repo.create(db, USER_ID, new).id


def _hero(html: str) -> str:
    return _html.text_of(html, accounts.reconcile_difference)


def _txn_count(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


def test_asset_dialog_starts_at_zero_difference(client: TestClient, db: sqlite3.Connection) -> None:
    acc = _asset(db)
    r = client.get(f"/accounts/{acc}/reconcile")
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.exists(r.text, accounts.reconcile_dialog)
    assert _hero(r.text) == "0.00"
    assert "100.00 PLN" in _html.text_of(r.text, accounts.reconcile_dialog)
    assert _html.resolve_one(r.text, accounts.reconcile_actual)["value"] == ""


def test_preview_shows_the_signed_difference_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _asset(db)
    before = _txn_count(db)
    r = client.post(f"/accounts/{acc}/reconcile?preview=1", data={"actual_balance": "70.00"})
    assert r.status_code == 200
    assert _hero(r.text) == "\N{MINUS SIGN}30.00"
    assert _html.resolve_one(r.text, accounts.reconcile_actual)["value"] == "70.00"
    assert _txn_count(db) == before


def test_limited_liability_is_asked_for_available_credit(
    client: TestClient, db: sqlite3.Connection
) -> None:
    card = _visa(db)
    r = client.post(f"/accounts/{card}/reconcile?preview=1", data={"actual_balance": "4000.00"})
    assert _hero(r.text) == "+234.56"
    assert _html.text_of(r.text, accounts.reconcile_available_help) == (
        "enter what you can still spend (limit \N{MINUS SIGN} spent). "
        "Limit 5,000.00 PLN · implied used 1,234.56 PLN"
    )
    fresh = client.get(f"/accounts/{card}/reconcile")
    assert _html.resolve_one(fresh.text, accounts.reconcile_available)["value"] == "3765.44"
    assert _hero(fresh.text) == "0.00"


def test_preview_of_an_impossible_available_is_422(
    client: TestClient, db: sqlite3.Connection
) -> None:
    card = _visa(db)
    r = client.post(f"/accounts/{card}/reconcile?preview=1", data={"actual_balance": "5000.01"})
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.exists(r.text, accounts.form_errors)


def test_submit_swaps_the_row_closes_the_dialog_and_flashes(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _asset(db)
    r = client.post(f"/accounts/{acc}/reconcile", data={"actual_balance": "70.00"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True, "forecast-stale": True}
    assert "70.00" in _html.text_of(r.text, accounts.row(acc))
    assert _html.text_of(r.text, shell.modal_root) == ""
    assert "Checking reconciled" in _html.text_of(r.text, shell.flash_region)
    adjustment = db.execute(
        "SELECT t.amount FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.account_id = ? AND c.direction = 'adjustment'",
        (acc,),
    ).fetchall()
    assert [row[0] for row in adjustment] == [-3_000]
