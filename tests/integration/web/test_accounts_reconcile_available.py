"""T-D52 — reconcile liability accounts by available credit."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import balance as balance_service

USER_ID = 1


def _make_card(settings: Settings, *, limit: int | None, liability: bool = True) -> int:
    conn = get_connection(settings)
    try:
        return accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa T-D52",
                currency="PLN",
                is_liability=liability,
                credit_limit_minor=limit,
                opening_balance=-123_456,
            ),
        ).id
    finally:
        conn.close()


def _balance(settings: Settings, account_id: int) -> int:
    conn = get_connection(settings)
    try:
        return balance_service.derive_balance(conn, USER_ID, account_id)
    finally:
        conn.close()


def test_form_liability_with_limit_asks_available(client: TestClient, _migrated: Settings) -> None:
    card = _make_card(_migrated, limit=500_000)
    r = client.get(f"/accounts/{card}/reconcile")
    assert r.status_code == 200
    assert ">Available<" in r.text
    assert 'value="3765.44"' in r.text
    assert "Limit 5,000.00" in r.text
    assert "1,234.56" in r.text


def test_submit_sets_available(client: TestClient, _migrated: Settings) -> None:
    card = _make_card(_migrated, limit=500_000)
    r = client.post(f"/accounts/{card}/reconcile", data={"actual_balance": "4000.00"})
    assert r.status_code == 200
    assert _balance(_migrated, card) == -100_000
    assert "Available 4,000.00 ·" in client.get("/accounts").text


def test_available_equals_limit_zeroes_used(client: TestClient, _migrated: Settings) -> None:
    card = _make_card(_migrated, limit=500_000)
    r = client.post(f"/accounts/{card}/reconcile", data={"actual_balance": "5000"})
    assert r.status_code == 200
    assert _balance(_migrated, card) == 0


@pytest.mark.parametrize("value", ["-1", "5000.01", "abc"])
def test_rejects_bad_available(client: TestClient, _migrated: Settings, value: str) -> None:
    card = _make_card(_migrated, limit=500_000)
    r = client.post(f"/accounts/{card}/reconcile", data={"actual_balance": value})
    assert r.status_code == 422
    assert _balance(_migrated, card) == -123_456


def test_liability_without_limit_enters_balance(client: TestClient, _migrated: Settings) -> None:
    card = _make_card(_migrated, limit=None)
    assert ">Available<" not in client.get(f"/accounts/{card}/reconcile").text
    client.post(f"/accounts/{card}/reconcile", data={"actual_balance": "-200.00"})
    assert _balance(_migrated, card) == -20_000


def test_asset_enters_balance(client: TestClient, _migrated: Settings) -> None:
    acc = _make_card(_migrated, limit=500_000, liability=False)
    assert ">Available<" not in client.get(f"/accounts/{acc}/reconcile").text
    client.post(f"/accounts/{acc}/reconcile", data={"actual_balance": "50.00"})
    assert _balance(_migrated, acc) == 5_000
