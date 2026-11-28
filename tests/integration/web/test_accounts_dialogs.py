"""Account dialogs on the shared shell: new, edit, delete, row menu (T-UR08b)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
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
from tests.ui_map import _html, accounts, shell
from tests.ui_map.locator import by_id, role

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
    amount = _html.resolve_one(r.text, accounts.form_opening_balance)
    assert (amount["name"], amount["value"]) == ("opening_balance", "0.00")
    form = _html.resolve_one(r.text, accounts.form_name).find_parent("form")
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
    assert _html.resolve_one(r.text, accounts.form_name)["value"] == "Keep me"
    assert _html.resolve_one(r.text, accounts.form_currency)["aria-invalid"] == "true"
    assert "ISO 4217 code required" in _html.text_of(r.text, by_id("field-currency-error"))
    assert _html.resolve_one(r.text, accounts.form_opening_balance)["value"] == "12.50"
    options = _html.resolve(r.text, role("option").inside(accounts.form_type))
    assert [o["value"] for o in options if o.has_attr("selected")] == ["cash"]
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_edit_dialog_prefills_and_freezes_the_currency(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Savings", type="savings")
    r = client.get(f"/accounts/{acc}/edit")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.edit_dialog("Savings"))
    assert _html.resolve_one(r.text, accounts.form_name)["value"] == "Savings"
    assert _html.resolve_one(r.text, accounts.form_currency).has_attr("readonly")
    options = _html.resolve(r.text, role("option").inside(accounts.form_type))
    assert [o["value"] for o in options if o.has_attr("selected")] == ["savings"]
    form = _html.resolve_one(r.text, accounts.form_name).find_parent("form")
    assert form is not None
    assert form["hx-target"] == f"#account-{acc}"


@pytest.mark.parametrize("liability", [False, True])
def test_edit_dialog_shows_the_kind_read_only(
    client: TestClient, db: sqlite3.Connection, *, liability: bool
) -> None:
    acc = _account(db, is_liability=liability, credit_limit_minor=100_000 if liability else None)
    r = client.get(f"/accounts/{acc}/edit")
    assert r.status_code == 200
    kind = _html.resolve_one(r.text, accounts.form_counts_as)
    assert (kind["value"], kind.has_attr("readonly")) == (
        "liability" if liability else "asset",
        True,
    )
    assert not _html.exists(r.text, accounts.form_liability)
    assert not _html.exists(r.text, accounts.form_counts_as_toggle)


def test_new_dialog_keeps_the_kind_toggle(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert _html.exists(r.text, accounts.form_liability)


def test_update_swaps_the_row_closes_the_dialog_and_flashes(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db)
    r = client.post(f"/accounts/{acc}", data={"name": "Renamed", "type": "cash"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True}
    assert _html.text_of(r.text, accounts.row(acc)).startswith("Renamed ")
    assert _html.text_of(r.text, shell.modal_root) == ""
    assert "Renamed saved" in _html.text_of(r.text, shell.flash_region)
    stored = accounts_repo.find_by_id(db, USER_ID, acc)
    assert stored is not None
    assert stored.name == "Renamed"


def test_update_validation_error_keeps_the_row_and_reopens_the_dialog(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, is_liability=True, credit_limit_minor=100_000)
    r = client.post(
        f"/accounts/{acc}", data={"name": "V", "is_liability": "on", "credit_limit": ""}
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    limit = _html.resolve_one(r.text, accounts.form_credit_limit)
    assert limit["aria-invalid"] == "true"
    assert not limit.has_attr("disabled")


def test_delete_dialog_confirms_when_nothing_points_at_the_account(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Empty")
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.delete_dialog("Empty"))
    assert _html.exists(r.text, accounts.delete_confirm)
    form = _html.resolve_one(r.text, accounts.delete_confirm).find_parent("form")
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
    assert _html.resolve_one(r.text, accounts.blocked_ok).find_parent("form") is None


def test_delete_dialog_for_a_missing_or_foreign_account_is_404(client: TestClient) -> None:
    assert client.get("/accounts/9999/edit?intent=delete").status_code == 404


def test_row_menu_offers_reconcile_edit_and_delete_dialogs(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Main")
    r = client.get("/accounts")
    menu = by_id(f"account-menu-{acc}")
    items = {
        a.get_text(): (a["hx-get"], a["class"])
        for a in _html.resolve(r.text, role("menuitem").inside(menu))
        if a.has_attr("hx-get")
    }
    assert items["reconcile"][0] == f"/accounts/{acc}/reconcile"
    assert "rd-menu__item--phone" in items["reconcile"][1]
    assert items["edit"][0] == f"/accounts/{acc}/edit"
    assert items["delete"][0] == f"/accounts/{acc}/edit?intent=delete"
    assert "rd-menu__item--danger" in items["delete"][1]


def test_create_without_a_name_is_the_human_422_summary_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection
) -> None:
    r = client.post("/accounts", data={"currency": "PLN"})
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
    assert not r.text.lstrip().startswith("{")
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0


def test_new_dialog_form_carries_the_account_form_id_itself(client: TestClient) -> None:
    r = client.get("/accounts/new")
    form = _html.resolve_one(r.text, accounts.account_form)
    assert form.name == "form"
    assert form["hx-target"] == "#account-form"
