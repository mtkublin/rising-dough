"""T-032 accounts router."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import balance as balance_service
from tests.ui_map import _html, accounts

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 — test-only fixed table names


@pytest.fixture
def acc_id(_migrated: Settings) -> int:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        return acc.id
    finally:
        conn.close()


def test_new_form_fragment(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    assert 'name="currency"' in r.text


def test_create_account(client: TestClient) -> None:
    r = client.post(
        "/accounts",
        data={"name": "Travel", "currency": "EUR", "opening_balance": "100.00"},
    )
    assert r.status_code == 200
    assert "Travel" in r.text
    assert "balance-stale" in r.headers["HX-Trigger"]


def test_create_rejects_bad_currency(client: TestClient) -> None:
    r = client.post(
        "/accounts",
        data={"name": "X", "currency": "EURO", "opening_balance": "0"},
    )
    assert r.status_code == 422
    assert "currency" in r.text


def test_create_rejects_blank_name(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={"name": "   ", "currency": "PLN", "opening_balance": "0"},
    )
    assert r.status_code == 422
    assert "<strong>name:</strong> name required" in r.text
    assert _count(db, "accounts") == before


def test_create_rejects_bad_opening(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={"name": "A", "currency": "PLN", "opening_balance": "nan!"},
    )
    assert r.status_code == 422
    assert "<strong>opening_balance:</strong> invalid number" in r.text
    assert _count(db, "accounts") == before


def test_edit_and_update(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/edit")
    assert r.status_code == 200
    r2 = client.post(f"/accounts/{acc_id}", data={"name": "Renamed", "type": "checking"})
    assert r2.status_code == 200
    assert "Renamed" in r2.text


def test_edit_404(client: TestClient) -> None:
    r = client.get("/accounts/9999/edit")
    assert r.status_code == 404
    assert "<strong>account:</strong> not found" in r.text


def test_update_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post("/accounts/9999", data={"name": "X"})
    assert r.status_code == 404
    assert "<strong>account:</strong> not found" in r.text
    assert _count(db, "accounts") == before


def test_update_blank_name(client: TestClient, acc_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/accounts/{acc_id}", data={"name": "   "})
    assert r.status_code == 422
    assert "<strong>name:</strong> name required" in r.text
    stored = accounts_repo.find_by_id(db, USER_ID, acc_id)
    assert stored is not None
    assert stored.name == "Main"


def test_delete(client: TestClient, acc_id: int, _migrated: Settings) -> None:
    r = client.post(f"/accounts/{acc_id}/delete")
    assert r.status_code == 200
    assert r.text == ""
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {
        "balance-stale": True,
        "forecast-stale": True,
        "toast": {"kind": "success", "message": "Account deleted"},
    }


def test_snapshot(client: TestClient, acc_id: int, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="X", direction=Direction.EXPENSE)
        )
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 1),
                category_id=cat.id,
                account_id=acc_id,
                amount=1000,
            ),
        )
    finally:
        conn.close()
    r = client.post(f"/accounts/{acc_id}/snapshot")
    assert r.status_code == 200
    assert "<li>" in r.text


def test_snapshot_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "audit_log")
    r = client.post("/accounts/9999/snapshot")
    assert r.status_code == 404
    assert r.text == "not found"
    assert _count(db, "audit_log") == before


def test_reconcile_form_renders(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/reconcile")
    assert r.status_code == 200
    assert "actual_balance" in r.text


def test_reconcile_form_404(client: TestClient) -> None:
    r = client.get("/accounts/9999/reconcile")
    assert r.status_code == 404
    assert "<strong>account:</strong> not found" in r.text or "not found" in r.text


def test_reconcile_submit(client: TestClient, acc_id: int) -> None:
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "123.45"})
    assert r.status_code == 200
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {"balance-stale": True, "forecast-stale": True}


def test_reconcile_submit_bad_number(
    client: TestClient, acc_id: int, db: sqlite3.Connection
) -> None:
    before = _count(db, "transactions")
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "notnum"})
    assert r.status_code == 422
    assert "<strong>actual_balance:</strong> invalid number" in r.text
    assert _count(db, "transactions") == before


def test_reconcile_submit_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "transactions")
    r = client.post("/accounts/9999/reconcile", data={"actual_balance": "1"})
    assert r.status_code == 404
    assert r.text == "not found"
    assert _count(db, "transactions") == before


def test_reconcile_zero_delta_still_200(
    client: TestClient, acc_id: int, db: sqlite3.Connection
) -> None:
    # Opening balance 0 - submitting 0 means no delta; the service raises
    # NoAdjustmentNeededError which the router swallows.
    before = _count(db, "transactions")
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "0"})
    assert r.status_code == 200
    assert f'id="account-{acc_id}"' in r.text
    assert _count(db, "transactions") == before
    assert balance_service.derive_balance(db, USER_ID, acc_id) == 0


# ---------------------------------------------------------------------------
# T-065 — Accounts polish


def _get_card(client: TestClient, acc_id: int) -> BeautifulSoup:
    r = client.get("/accounts")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    card = soup.find("article", id=f"account-{acc_id}")
    assert card is not None
    return BeautifulSoup(str(card), "html.parser")


# ---------------------------------------------------------------------------
# T-084 — Liability accounts: form, card, dashboard split (ADR-0024)


def test_create_credit_card_account_round_trips_limit(client: TestClient) -> None:
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
    assert "Credit card" in r.text
    assert "10,000.00" in r.text


def test_create_liability_without_limit_returns_422(client: TestClient) -> None:
    r = client.post(
        "/accounts",
        data={
            "name": "Visa",
            "currency": "PLN",
            "opening_balance": "0",
            "is_liability": "on",
            "credit_limit": "",
        },
    )
    assert r.status_code == 422
    assert "credit_limit" in r.text


def test_create_liability_with_zero_limit_rejected(
    client: TestClient, db: sqlite3.Connection
) -> None:
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={
            "name": "Visa",
            "currency": "PLN",
            "opening_balance": "0",
            "is_liability": "on",
            "credit_limit": "0",
        },
    )
    assert r.status_code == 422
    assert "<strong>credit_limit:</strong> positive credit limit required" in r.text
    assert _count(db, "accounts") == before


def test_update_asset_to_credit_card_sets_limit(client: TestClient, acc_id: int) -> None:
    r = client.post(
        f"/accounts/{acc_id}",
        data={
            "name": "Visa",
            "type": "credit_card",
            "is_liability": "on",
            "credit_limit": "5000.00",
        },
    )
    assert r.status_code == 200
    assert "5,000.00" in r.text


def test_update_credit_card_to_asset_clears_limit(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa",
                currency="PLN",
                is_liability=True,
                credit_limit_minor=1_000_000,
            ),
        )
    finally:
        conn.close()
    r = client.post(
        f"/accounts/{acc.id}",
        data={"name": "Visa", "type": "", "is_liability": "", "credit_limit": ""},
    )
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        after = accounts_repo.find_by_id(conn, USER_ID, acc.id)
    finally:
        conn.close()
    assert after is not None
    assert after.is_liability is False
    assert after.credit_limit_minor is None


# ---------------------------------------------------------------------------
# T-123 — Credit-limit field initial-render lockstep bug (ADR-0030 §6 contract).
#
# The sync `<script>` previously resolved the form via
# `document.currentScript.previousElementSibling`, which breaks when the form
# fragment is nested inside `partials/_slideover.html`. These tests pin the
# server-rendered contract: `hidden` + `aria-hidden="true"` on the limit label
# and `disabled` on the input must track `account is None or not
# account.is_liability` in lockstep.


def _limit_markup(html: str) -> tuple[Tag, Tag]:
    soup = BeautifulSoup(html, "html.parser")
    label = soup.find("label", attrs={"data-limit-field": True})
    assert isinstance(label, Tag), "credit-limit label with data-limit-field expected"
    limit_input = label.find("input", attrs={"name": "credit_limit"})
    assert isinstance(limit_input, Tag), "credit_limit input expected inside label"
    return label, limit_input


def test_new_form_hides_credit_limit_by_default(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    label, limit_input = _limit_markup(r.text)
    assert label.has_attr("hidden")
    assert label.get("aria-hidden") == "true"
    assert limit_input.has_attr("disabled")


def test_new_form_marks_form_root_for_sync(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", attrs={"data-account-form": True})
    assert isinstance(form, Tag), "account form must expose data-account-form hook"


def test_edit_form_shows_credit_limit_for_liability(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        visa = accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa",
                currency="PLN",
                is_liability=True,
                credit_limit_minor=1_000_000,
            ),
        )
    finally:
        conn.close()
    r = client.get(f"/accounts/{visa.id}/edit")
    assert r.status_code == 200
    label, limit_input = _limit_markup(r.text)
    assert not label.has_attr("hidden")
    assert label.get("aria-hidden") is None
    assert not limit_input.has_attr("disabled")


def test_edit_form_hides_credit_limit_for_asset(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/edit")
    assert r.status_code == 200
    label, limit_input = _limit_markup(r.text)
    assert label.has_attr("hidden")
    assert label.get("aria-hidden") == "true"
    assert limit_input.has_attr("disabled")


# ---------------------------------------------------------------------------
# T-D51 — Liability "Available" renders with 2 decimals.


def test_liability_available_shows_two_decimals(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa T-D51",
                currency="PLN",
                is_liability=True,
                credit_limit_minor=500_000,
                opening_balance=-123_456,
            ),
        )
    finally:
        conn.close()
    r = client.get("/accounts")
    assert r.status_code == 200
    assert "Available 3,765.44 ·" in r.text
    assert "Available 3,765 ·" not in r.text


def test_create_reloads_page_without_swap(client: TestClient) -> None:
    # T-D150: the accounts table has no region that refetches on a trigger.
    r = client.post(
        "/accounts",
        data={"name": "Travel", "currency": "EUR"},
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/accounts"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    assert "balance-stale" in r.headers["HX-Trigger"]


def test_new_form_targets_itself_not_accounts_grid(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert 'id="account-form"' in r.text
    assert 'hx-target="#account-form"' in r.text
    assert "#accounts-grid" not in r.text


def test_delete_refused_when_balance_not_zero(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings
) -> None:
    acc = accounts_repo.create(
        db, USER_ID, NewAccount(name="Funded", currency="PLN", opening_balance=500)
    )
    audit_before = _count(db, "audit_log")

    r = client.post(f"/accounts/{acc.id}/delete", headers={"HX-Request": "true"})

    assert r.status_code == 409
    assert "Cannot archive account: Balance is not zero" in r.text
    assert accounts_repo.find_by_id(db, USER_ID, acc.id) is not None
    assert _count(db, "audit_log") == audit_before


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
