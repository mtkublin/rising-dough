"""Saving a foreign-currency account with no cached FX rate (T-UR69, ADR-0139, ADR-0008)."""

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


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


NOTE = "rate unavailable for EUR: left out of totals"


def _post(client: TestClient, name: str, currency: str, opening: str) -> None:
    r = client.post(
        "/accounts", data={"name": name, "currency": currency, "opening_balance": opening}
    )
    assert r.status_code < 400, r.text


def _account_id(db: sqlite3.Connection, name: str) -> int:
    return int(db.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()[0])


def test_create_eur_account_without_rate_saves_and_lists(
    client: TestClient, db: sqlite3.Connection
) -> None:
    assert db.execute("SELECT COUNT(*) FROM fx_rates").fetchone()[0] == 0
    _post(client, "Euro Wallet", "EUR", "100.00")
    row = db.execute(
        "SELECT id, currency, opening_balance FROM accounts WHERE name = 'Euro Wallet'"
    ).fetchone()
    assert (row["currency"], row["opening_balance"]) == ("EUR", 10000)
    audit = db.execute(
        "SELECT entity_type, entity_id, operation FROM audit_log WHERE entity_type = 'account'"
    ).fetchall()
    assert [(a["entity_type"], a["entity_id"], a["operation"]) for a in audit] == [
        ("account", row["id"], "create")
    ]
    page = client.get("/accounts")
    assert page.status_code == 200
    assert _html.text_of(page.text, accounts.row(row["id"])).count("100.00 EUR") >= 1
    assert not _html.exists(page.text, accounts.new_account_cta)
    hero = _html.text_of(page.text, accounts.hero)
    assert "net worth" in hero
    assert "assets 0.00" in hero
    assert "liabilities 0.00" in hero
    assert "0.00 PLN" in hero
    assert "100.00" not in hero
    assert _html.text_of(page.text, accounts.rate_note) == NOTE


def test_mixed_pln_and_eur_totals_count_only_the_pln_account(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _post(client, "Zloty", "PLN", "250.00")
    _post(client, "Euro Wallet", "EUR", "100.00")
    page = client.get("/accounts")
    assert page.status_code == 200
    hero = _html.text_of(page.text, accounts.hero)
    assert "250.00" in hero
    assert "assets 250.00" in hero
    assert "350.00" not in hero
    assert _html.text_of(page.text, accounts.rate_note) == NOTE
    assert _html.exists(page.text, accounts.row(_account_id(db, "Zloty")))
    assert _html.exists(page.text, accounts.row(_account_id(db, "Euro Wallet")))


def test_other_users_accounts_are_absent(client: TestClient, db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    theirs = [
        accounts_repo.create(db, 2, NewAccount(name=name, currency=ccy, opening_balance=5000)).id
        for name, ccy in (("Their Euro", "EUR"), ("Their Zloty", "PLN"))
    ]
    db.commit()
    _post(client, "Mine", "PLN", "10.00")
    page = client.get("/accounts")
    assert page.status_code == 200
    assert [_html.exists(page.text, accounts.row(a)) for a in theirs] == [False, False]
    assert _html.exists(page.text, accounts.row(_account_id(db, "Mine")))
    assert not _html.exists(page.text, accounts.rate_note)
    assert "assets 10.00" in _html.text_of(page.text, accounts.hero)
