"""Account dialogs on the shared shell: new, edit, delete, row menu (T-UR08b)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from bs4 import BeautifulSoup
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
from tests.ui_map import _html, accounts

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _account(db: sqlite3.Connection, name: str = "Main", **kw: object) -> int:
    return accounts_repo.create(db, USER_ID, NewAccount(name=name, currency="PLN", **kw)).id  # type: ignore[arg-type]  # test helper forwards NewAccount kwargs


def test_new_dialog_is_a_standard_dialog_with_the_opening_balance_hero(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.exists(r.text, accounts.new_dialog)
    soup = BeautifulSoup(r.text, "html.parser")
    amount = soup.select_one("input.rd-dialog__amount")
    assert amount is not None
    assert (amount["name"], amount["value"]) == ("opening_balance", "0.00")
    form = soup.select_one("form.rd-dialog__form")
    assert form is not None
    assert form["hx-post"] == "/accounts"


def test_create_validation_error_reopens_the_dialog_with_the_entered_values(
    client: TestClient, db: sqlite3.Connection
) -> None:
    r = client.post(
        "/accounts",
        data={"name": "Keep me", "currency": "EURO", "opening_balance": "12.50", "type": "cash"},
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    soup = BeautifulSoup(r.text, "html.parser")
    name = soup.select_one("#field-name")
    currency = soup.select_one("#field-currency")
    assert name is not None
    assert currency is not None
    assert name["value"] == "Keep me"
    assert currency["aria-invalid"] == "true"
    assert "ISO 4217 code required" in soup.select_one("#field-currency-error").get_text()  # type: ignore[union-attr]
    assert soup.select_one("input.rd-dialog__amount")["value"] == "12.50"  # type: ignore[index]
    selected = soup.select_one("#field-type option[selected]")
    assert selected is not None
    assert selected["value"] == "cash"
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_edit_dialog_prefills_and_freezes_the_currency(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Savings", type="savings")
    r = client.get(f"/accounts/{acc}/edit")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.edit_dialog("Savings"))
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.select_one("#field-name")["value"] == "Savings"  # type: ignore[index]
    assert soup.select_one("#field-currency").has_attr("readonly")  # type: ignore[union-attr]
    assert soup.select_one("#field-type option[selected]")["value"] == "savings"  # type: ignore[index]
    assert soup.select_one("form.rd-dialog__form")["hx-target"] == f"#account-{acc}"  # type: ignore[index]


def test_update_swaps_the_row_closes_the_dialog_and_flashes(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db)
    r = client.post(f"/accounts/{acc}", data={"name": "Renamed", "type": "cash"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True}
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.select_one(f"tr#account-{acc} .rd-row__title").get_text() == "Renamed"  # type: ignore[union-attr]
    modal = soup.select_one("#modal-root")
    assert modal is not None
    assert modal.get_text() == ""
    assert "Renamed saved" in soup.select_one("#flash-region").get_text()  # type: ignore[union-attr]
    assert accounts_repo.find_by_id(db, USER_ID, acc).name == "Renamed"  # type: ignore[union-attr]


def test_update_validation_error_keeps_the_row_and_reopens_the_dialog(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db)
    r = client.post(
        f"/accounts/{acc}", data={"name": "V", "is_liability": "on", "credit_limit": ""}
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.select_one("#field-credit_limit")["aria-invalid"] == "true"  # type: ignore[index]
    assert not soup.select_one("#field-credit_limit").has_attr("disabled")  # type: ignore[union-attr]


def test_delete_dialog_confirms_when_nothing_points_at_the_account(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Empty")
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.delete_dialog("Empty"))
    assert _html.exists(r.text, accounts.delete_confirm)
    form = BeautifulSoup(r.text, "html.parser").select_one("form.rd-dialog__form")
    assert form is not None
    assert form["hx-post"] == f"/accounts/{acc}/delete"


def test_delete_dialog_is_blocked_by_a_live_transaction(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Used")
    cat = categories_repo.create(db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE))
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 10), category_id=cat.id, account_id=acc, amount=100
        ),
    )
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert _html.exists(r.text, accounts.blocked_dialog("Used"))
    assert not _html.exists(r.text, accounts.delete_confirm)
    assert "It still has 1 transaction. Move or delete them first." in _html.text_of(
        r.text, accounts.blocked_dialog("Used")
    )
    link = _html.resolve_one(r.text, accounts.blocked_link)
    assert link["href"] == f"/ledger?account_id={acc}&view=actual"
    assert link.get_text() == "view 1 transaction"
    assert BeautifulSoup(r.text, "html.parser").select_one("form") is None


def test_delete_dialog_for_a_missing_or_foreign_account_is_404(client: TestClient) -> None:
    assert client.get("/accounts/9999/edit?intent=delete").status_code == 404


def test_row_menu_offers_reconcile_edit_and_delete_dialogs(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Main")
    r = client.get("/accounts")
    soup = BeautifulSoup(r.text, "html.parser")
    items = {
        a.get_text(): (a["hx-get"], a["class"])
        for a in soup.select(f"#account-menu-{acc} a[hx-get]")
    }
    assert items["reconcile"][0] == f"/accounts/{acc}/reconcile"
    assert "rd-menu__item--phone" in items["reconcile"][1]
    assert items["edit"][0] == f"/accounts/{acc}/edit"
    assert items["delete"][0] == f"/accounts/{acc}/edit?intent=delete"
    assert "rd-menu__item--danger" in items["delete"][1]
