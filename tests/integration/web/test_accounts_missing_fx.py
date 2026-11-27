"""Saving a foreign-currency account with no cached FX rate (T-UR69, ADR-0139, ADR-0008)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.ui_map import _html, accounts


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def test_create_eur_account_without_rate_saves_and_lists(
    client: TestClient, db: sqlite3.Connection
) -> None:
    assert db.execute("SELECT COUNT(*) FROM fx_rates").fetchone()[0] == 0
    before = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    r = client.post(
        "/accounts",
        data={"name": "Euro Wallet", "currency": "EUR", "opening_balance": "100.00"},
    )
    assert r.status_code < 400, r.text
    row = db.execute(
        "SELECT id, currency, opening_balance FROM accounts WHERE name = 'Euro Wallet'"
    ).fetchone()
    assert (row["currency"], row["opening_balance"]) == ("EUR", 10000)
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] > before
    page = client.get("/accounts")
    assert page.status_code == 200
    assert _html.exists(page.text, accounts.row(row["id"]))
    assert not _html.exists(page.text, accounts.new_account_cta)
    assert "rate unavailable for EUR: left out of totals" in _html.text_of(
        page.text, accounts.rate_note
    )
