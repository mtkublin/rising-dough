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
from tests.ui_map import _html, accounts, errors, rd_shell, shell
from tests.ui_map.locator import role

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
    assert _html.exists(r.text, accounts.form_currency)


def test_create_account(client: TestClient) -> None:
    r = client.post(
        "/accounts",
        data={"name": "Travel", "currency": "EUR", "opening_balance": "100.00"},
    )
    assert r.status_code == 200
    assert "Travel" in _html.all_text(r.text, accounts.any_row)
    assert "balance-stale" in r.headers["HX-Trigger"]


def test_create_rejects_bad_currency(client: TestClient) -> None:
    r = client.post(
        "/accounts",
        data={"name": "X", "currency": "EURO", "opening_balance": "0"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-currency-error": "▲ ISO 4217 code required",
    }
    assert r.headers["HX-Retarget"] == "#modal-root"


def test_create_rejects_unknown_currency_code(client: TestClient, db: sqlite3.Connection) -> None:
    """A well-formed code outside ISO 4217 (XYZ) is a 422 under the field; nothing is written."""
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={"name": "Mystery", "currency": "xyz", "opening_balance": "0"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-currency-error": "▲ Unknown currency code",
    }
    assert _count(db, "accounts") == before


def test_create_rejects_blank_name(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={"name": "   ", "currency": "PLN", "opening_balance": "0"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
    assert _count(db, "accounts") == before


def test_create_rejects_bad_opening(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post(
        "/accounts",
        data={"name": "A", "currency": "PLN", "opening_balance": "nan!"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-opening_balance-error": "▲ invalid number",
    }
    assert _count(db, "accounts") == before


def test_edit_and_update(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/edit")
    assert r.status_code == 200
    r2 = client.post(f"/accounts/{acc_id}", data={"name": "Renamed", "type": "checking"})
    assert r2.status_code == 200
    assert "Renamed" in _html.all_text(r2.text, accounts.any_row)


def test_edit_404(client: TestClient) -> None:
    r = client.get("/accounts/9999/edit")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"


def test_update_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "accounts")
    r = client.post("/accounts/9999", data={"name": "X"})
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _count(db, "accounts") == before


def test_update_blank_name(client: TestClient, acc_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/accounts/{acc_id}", data={"name": "   "})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
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
        "toast": {"variant": "success", "message": "Account deleted"},
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
    assert _html.exists(r.text, accounts.snapshot_item)


def test_snapshot_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "audit_log")
    r = client.post("/accounts/9999/snapshot")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _count(db, "audit_log") == before


def test_reconcile_form_renders(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/reconcile")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.reconcile_actual)


def test_reconcile_form_404(client: TestClient) -> None:
    r = client.get("/accounts/9999/reconcile")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"


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
    assert _html.error_lines(r.text) == {
        "field-actual_balance-error": "▲ invalid number",
    }
    assert _count(db, "transactions") == before


def test_reconcile_submit_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _count(db, "transactions")
    r = client.post("/accounts/9999/reconcile", data={"actual_balance": "1"})
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _count(db, "transactions") == before


def test_reconcile_zero_delta_still_200(
    client: TestClient, acc_id: int, db: sqlite3.Connection
) -> None:
    # Opening balance 0 - submitting 0 means no delta; the service raises
    # NoAdjustmentNeededError which the router swallows.
    before = _count(db, "transactions")
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "0"})
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.row(acc_id))
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
    card = _html.all_text(r.text, accounts.any_row)
    assert "credit card" in card
    assert "10,000.00" in card


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
    assert _html.error_lines(r.text) == {
        "field-credit_limit-error": "▲ positive credit limit required",
    }


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
    assert _html.error_lines(r.text) == {
        "field-credit_limit-error": "▲ positive credit limit required",
    }
    assert _count(db, "accounts") == before


def test_update_liability_limit_is_saved(client: TestClient, _migrated: Settings) -> None:
    acc_id = _create(
        _migrated, name="Main", currency="PLN", is_liability=True, credit_limit_minor=100_000
    )
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
    assert "5,000.00" in _html.all_text(r.text, accounts.any_row)


def _stored(settings: Settings, account: int) -> object:
    conn = get_connection(settings)
    try:
        return accounts_repo.find_by_id(conn, USER_ID, account)
    finally:
        conn.close()


def test_update_cannot_turn_a_liability_into_an_asset(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings
) -> None:
    acc = _create(
        _migrated, name="Visa", currency="PLN", is_liability=True, credit_limit_minor=1_000_000
    )
    audit_before = _count(db, "audit_log")
    r = client.post(
        f"/accounts/{acc}",
        data={"name": "Renamed", "type": "", "is_liability": "", "credit_limit": ""},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-is_liability-error": "▲ can't be changed after the account is created",
    }
    after = _stored(_migrated, acc)
    assert (after.name, after.is_liability, after.credit_limit_minor) == ("Visa", True, 1_000_000)  # type: ignore[attr-defined]  # find_by_id is Account here
    assert _count(db, "audit_log") == audit_before


def test_update_cannot_turn_an_asset_into_a_liability(
    client: TestClient, db: sqlite3.Connection, acc_id: int, _migrated: Settings
) -> None:
    audit_before = _count(db, "audit_log")
    r = client.post(
        f"/accounts/{acc_id}",
        data={"name": "Main", "type": "", "is_liability": "on", "credit_limit": "5000.00"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-is_liability-error": "▲ can't be changed after the account is created",
    }
    after = _stored(_migrated, acc_id)
    assert (after.is_liability, after.credit_limit_minor) == (False, None)  # type: ignore[attr-defined]  # find_by_id is Account here
    assert _count(db, "audit_log") == audit_before


def test_update_with_the_same_kind_saves(client: TestClient, _migrated: Settings) -> None:
    acc = _create(
        _migrated, name="Visa", currency="PLN", is_liability=True, credit_limit_minor=1_000_000
    )
    r = client.post(
        f"/accounts/{acc}",
        data={"name": "Visa 2", "type": "", "is_liability": "on", "credit_limit": "2000.00"},
    )
    assert r.status_code == 200
    after = _stored(_migrated, acc)
    assert (after.name, after.is_liability, after.credit_limit_minor) == ("Visa 2", True, 200_000)  # type: ignore[attr-defined]  # find_by_id is Account here


# ---------------------------------------------------------------------------
# T-123, T-UR08b: the credit-limit field's server-rendered state tracks the liability radio.
# reveal.js toggles ``hidden`` and ``disabled`` on ``data-show-when`` parts; the server renders the
# initial state (a disabled field carries ``data-reveal-disabled`` so reveal.js can enable it).


def _limit(html: str) -> tuple[Tag, Tag]:
    limit_input = _html.resolve_one(html, accounts.form_credit_limit)
    label = limit_input.find_parent("label")
    assert isinstance(label, Tag)
    return label, limit_input


def test_new_form_hides_credit_limit_by_default(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    label, limit_input = _limit(r.text)
    assert label.has_attr("hidden")
    assert label["data-show-when"] == "is_liability=on"
    assert limit_input.has_attr("disabled")
    assert limit_input.has_attr("data-reveal-disabled")


def test_new_dialog_lists_every_iso_currency_in_the_datalist(client: TestClient) -> None:
    r = client.get("/accounts/new")
    options = _html.resolve(r.text, role("option").inside(accounts.currency_options))
    codes = [o["value"] for o in options]
    assert {"PLN", "EUR", "USD"} <= set(codes)
    assert len(codes) == len(set(codes)) > 100
    assert _html.resolve_one(r.text, accounts.form_currency)["list"] == "iso-codes"


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
    label, limit_input = _limit(r.text)
    assert not label.has_attr("hidden")
    assert not limit_input.has_attr("disabled")
    assert limit_input["value"] == "10000.00"
    assert _html.resolve_one(r.text, accounts.form_currency).has_attr("readonly")


def test_edit_form_hides_credit_limit_for_asset(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/edit")
    assert r.status_code == 200
    label, limit_input = _limit(r.text)
    assert label.has_attr("hidden")
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
    cards = _html.all_text(r.text, accounts.any_row)
    assert "available 3,765.44 of 5,000.00" in cards
    assert "available 3,765 of" not in cards


def test_create_flashes_and_refetches_without_reload(client: TestClient) -> None:
    # T-D150: the accounts table has no region that refetches on a trigger.
    r = client.post(
        "/accounts",
        data={"name": "Travel", "currency": "EUR"},
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/accounts"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers
    assert "Travel created" in _html.text_of(r.text, rd_shell.flash_saved)
    assert "balance-stale" in r.headers["HX-Trigger"]


def test_new_form_targets_itself_not_accounts_grid(client: TestClient) -> None:
    r = client.get("/accounts/new")
    form = _html.resolve_one(r.text, accounts.account_form)
    assert form["hx-target"] == "#account-form"
    assert "#accounts-grid" not in str(form)


def test_delete_refused_when_balance_not_zero(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings
) -> None:
    acc = accounts_repo.create(
        db, USER_ID, NewAccount(name="Funded", currency="PLN", opening_balance=500)
    )
    audit_before = _count(db, "audit_log")

    r = client.post(f"/accounts/{acc.id}/delete", headers={"HX-Request": "true"})

    assert r.status_code == 409
    assert "Cannot archive account: Balance is not zero" in _html.all_text(
        r.text, shell.flash_region
    )
    assert accounts_repo.find_by_id(db, USER_ID, acc.id) is not None
    assert _count(db, "audit_log") == audit_before


def test_delete_refused_while_live_transaction_references_account(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings
) -> None:
    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Used", currency="PLN"))
    cat = categories_repo.create(db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE))
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 10), category_id=cat.id, account_id=acc.id, amount=1
        ),
    )
    audit_before = _count(db, "audit_log")

    r = client.post(f"/accounts/{acc.id}/delete", headers={"HX-Request": "true"})

    assert r.status_code == 409
    assert (
        "Cannot archive account: Balance is not zero; 1 transaction uses this account"
        in _html.all_text(r.text, shell.flash_region)
    )
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
    acc = _create(
        _migrated, name="Main", currency="PLN", is_liability=True, credit_limit_minor=100_000
    )
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
