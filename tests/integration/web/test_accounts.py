"""Accounts page rendering through the UI map (T-032, T-084, T-D51, T-D150).

Status codes, HX headers, CSRF, ownership and DB / audit effects live in
``tests/contract/test_accounts.py``; this file keeps the rendered-content
checks, expressed as UI-map lookups (ADR-0106 section 2).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from tests.ui_map import _html, accounts

USER_ID = 1


def _create(settings: Settings, **kwargs: object) -> int:
    conn = get_connection(settings)
    try:
        return accounts_repo.create(conn, USER_ID, NewAccount(**kwargs)).id  # type: ignore[arg-type]
    finally:
        conn.close()


def _latest_id(settings: Settings) -> int:
    conn = get_connection(settings)
    try:
        return max(a.id for a in accounts_repo.list_all(conn, USER_ID))
    finally:
        conn.close()


def test_index_shows_each_account_row_with_its_name(
    client: TestClient, _migrated: Settings
) -> None:
    acc = _create(_migrated, name="Main", currency="PLN", opening_balance=12_345)
    html = client.get("/accounts").text
    text = _html.text_of(html, accounts.row(acc))
    assert "Main" in text
    assert "123.45" in text


def test_create_credit_card_round_trips_limit(client: TestClient, _migrated: Settings) -> None:
    r = client.post(
        "/accounts",
        data={
            "name": "Visa",
            "currency": "PLN",
            "opening_balance": "0",
            "is_liability": "on",
            "credit_limit": "10000.00",
        },
    )
    assert r.status_code == 200
    text = _html.text_of(r.text, accounts.row(_latest_id(_migrated)))
    assert "credit card" in text.lower()
    assert "10,000.00" in text


def test_create_returns_the_new_row(client: TestClient, _migrated: Settings) -> None:
    r = client.post(
        "/accounts", data={"name": "Travel", "currency": "EUR", "opening_balance": "100.00"}
    )
    assert "Travel" in _html.text_of(r.text, accounts.row(_latest_id(_migrated)))


def test_update_credit_card_limit_is_shown_in_the_row(
    client: TestClient, _migrated: Settings
) -> None:
    acc = _create(_migrated, name="Main", currency="PLN")
    r = client.post(
        f"/accounts/{acc}",
        data={
            "name": "Visa",
            "type": "credit_card",
            "is_liability": "on",
            "credit_limit": "5000.00",
        },
    )
    assert "5,000.00" in _html.text_of(r.text, accounts.row(acc))


def test_liability_available_shows_two_decimals(client: TestClient, _migrated: Settings) -> None:
    card = _create(
        _migrated,
        name="Visa T-D51",
        currency="PLN",
        is_liability=True,
        credit_limit_minor=500_000,
        opening_balance=-123_456,
    )
    text = _html.text_of(client.get("/accounts").text, accounts.row(card))
    assert "Available 3,765.44 \u00b7" in text
    assert "Available 3,765 \u00b7" not in text
