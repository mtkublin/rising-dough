"""The edit-transaction dialog: open, save, 422, delete and undo (T-UR09b, ADR-0107, ADR-0152).

The dialog posts the picker's ``category`` (the old ``category_id`` still works). A missing field is
a human 422 that re-renders the dialog with the posted values; nothing is written.
"""

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
from budget_planner.domain.money import sign_glyph
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.auth_support import seed_login_user
from tests.ui_map import _html, entries, ledger, rd_shell

USER_ID = 1
FROM_DIALOG = {"HX-Request": "true", "HX-Target": "modal-root"}
ON_LEDGER = {**FROM_DIALOG, "HX-Current-URL": "http://testserver/ledger?view=actual"}
ON_TODAY = {**FROM_DIALOG, "HX-Current-URL": "http://testserver/today"}
HX = {"HX-Request": "true"}
STALE = {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}
TRANSIT_GLYPH = "\N{RIGHTWARDS ARROW OVER LEFTWARDS ARROW}"


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    pln = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    pln2 = accounts_repo.create(db, USER_ID, NewAccount(name="Savings", currency="PLN"))
    eur = accounts_repo.create(db, USER_ID, NewAccount(name="Euro", currency="EUR"))
    jpy = accounts_repo.create(db, USER_ID, NewAccount(name="Yen", currency="JPY"))
    groc = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    salary = categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    move = categories_repo.create(
        db, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT)
    )
    return {
        "pln": pln.id,
        "pln2": pln2.id,
        "eur": eur.id,
        "jpy": jpy.id,
        "groc": groc.id,
        "salary": salary.id,
        "move": move.id,
    }


def _txn(
    db: sqlite3.Connection,
    account: int,
    category: int,
    amount: int,
    *,
    note: str = "milk",
    dest: int | None = None,
) -> int:
    return transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 10, 31),
            category_id=category,
            account_id=account,
            amount=amount,
            description=note,
            dest_account_id=dest,
        ),
    ).id


def _row(db: sqlite3.Connection, txn_id: int) -> tuple[int, int, int, str, str, int | None]:
    r = db.execute(
        "SELECT amount, category_id, account_id, description, operation_date, dest_account_id "
        "FROM transactions WHERE id = ?",
        (txn_id,),
    ).fetchone()
    return (r[0], r[1], r[2], r[3], r[4], r[5])


def _ops(db: sqlite3.Connection, txn_id: int) -> list[str]:
    rows = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = 'transaction' AND entity_id = ? "
        "ORDER BY id",
        (txn_id,),
    ).fetchall()
    return [r[0] for r in rows]


def _form(ids: dict[str, int], **over: str | int) -> dict[str, str | int]:
    base: dict[str, str | int] = {
        "category": ids["groc"],
        "account_id": ids["pln"],
        "amount": "77.25",
        "operation_date": "2026-11-02",
        "description": "edited",
    }
    return {**base, **over}


def test_the_dialog_opens_prefilled_with_the_stored_values(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    r = client.get(f"/transactions/{txn_id}/edit", headers=HX)

    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    dialog = _html.resolve_one(r.text, entries.edit_dialog)
    assert dialog.get("aria-labelledby") == "edit-transaction-dialog-title"
    assert _html.text_of(r.text, entries.edit_dialog_title) == "edit transaction · Groceries"
    form = dialog.find("form")
    assert form is not None
    assert form.get("hx-post") == f"/transactions/{txn_id}"
    assert _html.resolve_one(r.text, entries.edit_amount).get("value") == "35.50"
    assert ledger.control(r.text, entries.field_date).get("value") == "2026-10-31"
    assert ledger.control(r.text, entries.field_note).get("value") == "milk"
    assert _html.resolve_one(r.text, entries.category_option("Groceries")).has_attr("checked")
    account = ledger.control(r.text, entries.field_account)
    chosen = account.find("option", selected=True)
    assert chosen is not None
    assert chosen.get("value") == str(ids["pln"])
    hero = _html.all_text(r.text, entries.edit_dialog)
    assert sign_glyph(True) in hero
    assert "PLN" in hero


def test_a_euro_amount_is_shown_in_the_account_currency(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["eur"], ids["salary"], 123_45)

    r = client.get(f"/transactions/{txn_id}/edit", headers=HX)

    assert _html.resolve_one(r.text, entries.edit_amount).get("value") == "123.45"
    hero = _html.all_text(r.text, entries.edit_dialog)
    assert sign_glyph(False) in hero
    assert "EUR" in hero


def test_a_yen_amount_has_no_decimals(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["jpy"], ids["groc"], 5000)

    r = client.get(f"/transactions/{txn_id}/edit", headers=HX)

    assert _html.resolve_one(r.text, entries.edit_amount).get("value") == "5000"
    assert "JPY" in _html.all_text(r.text, entries.edit_dialog)


def test_a_transit_opens_with_both_accounts_and_the_transit_sign(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["move"], 2193, dest=ids["pln2"])

    r = client.get(f"/transactions/{txn_id}/edit", headers=HX)

    assert _html.resolve_one(r.text, entries.edit_amount).get("value") == "21.93"
    assert TRANSIT_GLYPH in _html.all_text(r.text, entries.edit_dialog)
    dest = ledger.control(r.text, entries.edit_dest)
    chosen = dest.find("option", selected=True)
    assert chosen is not None
    assert chosen.get("value") == str(ids["pln2"])
    wrapper = dest.find_parent(attrs={"data-show-when": True})
    assert wrapper is not None
    assert not wrapper.has_attr("hidden")


def test_the_hero_refresh_follows_the_account_and_category(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    r = client.get(
        f"/transactions/{txn_id}/edit",
        params={
            "hero": "1",
            "account_id": str(ids["eur"]),
            "category": str(ids["salary"]),
            "amount": "10.00",
        },
        headers=HX,
    )

    hero = _html.all_text(r.text, entries.edit_dialog)
    assert "EUR" in hero
    assert sign_glyph(False) in hero
    assert _html.resolve_one(r.text, entries.edit_amount).get("value") == "10.00"
    assert "HX-Retarget" not in r.headers


def test_a_plain_page_load_gets_the_shell_that_asks_for_the_dialog(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    r = client.get(f"/transactions/{txn_id}/edit")

    assert r.status_code == 200
    opener = _html.resolve_one(r.text, entries.edit_opener)
    assert opener.get("hx-get") == f"/transactions/{txn_id}/edit"
    assert _html.count(r.text, entries.edit_dialog) == 0


def test_unknown_and_other_users_ids_are_404(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    their_acc = accounts_repo.create(db, other, NewAccount(name="Theirs", currency="PLN"))
    their_cat = categories_repo.create(
        db, other, NewCategory(name="Theirs", direction=Direction.EXPENSE)
    )
    theirs = transactions_repo.create(
        db,
        other,
        NewTransaction(
            operation_date=date(2026, 10, 1),
            category_id=their_cat.id,
            account_id=their_acc.id,
            amount=999,
            description="secret",
        ),
    ).id

    assert client.get("/transactions/99999/edit", headers=HX).status_code == 404
    assert client.get(f"/transactions/{theirs}/edit", headers=HX).status_code == 404
    assert client.get(f"/transactions/{theirs}/edit?hero=1", headers=HX).status_code == 404
    post = client.post(f"/transactions/{theirs}", data=_form(ids), headers=FROM_DIALOG)
    assert post.status_code == 404
    assert _row(db, theirs) == (999, their_cat.id, their_acc.id, "secret", "2026-10-01", None)
    assert _ops(db, theirs) == ["create"]


def test_save_updates_the_row_audits_it_and_closes_the_dialog(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    r = client.post(f"/transactions/{txn_id}", data=_form(ids), headers=ON_LEDGER)

    assert r.status_code == 200
    assert _row(db, txn_id) == (7725, ids["groc"], ids["pln"], "edited", "2026-11-02", None)
    assert _ops(db, txn_id) == ["create", "update"]
    assert json.loads(r.headers["HX-Trigger"]) == STALE
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers
    assert _html.text_of(r.text, rd_shell.flash_saved) == "● transaction saved"
    assert _html.text_of(r.text, rd_shell.modal_root) == ""


def test_save_off_the_ledger_reloads_the_page(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    r = client.post(f"/transactions/{txn_id}", data=_form(ids), headers=ON_TODAY)

    assert r.status_code == 200
    assert r.headers["HX-Refresh"] == "true"
    assert _row(db, txn_id)[0] == 7725


def test_save_keeps_the_stored_amount_exponent_for_yen_and_euro(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    yen = _txn(db, ids["jpy"], ids["groc"], 5000)
    euro = _txn(db, ids["eur"], ids["groc"], 1000)

    client.post(
        f"/transactions/{yen}",
        data=_form(ids, account_id=ids["jpy"], amount="6000"),
        headers=ON_LEDGER,
    )
    client.post(
        f"/transactions/{euro}",
        data=_form(ids, account_id=ids["eur"], amount="12.34"),
        headers=ON_LEDGER,
    )

    assert _row(db, yen)[0] == 6000
    assert _row(db, euro)[0] == 1234


def test_the_old_category_id_field_still_saves(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)
    data = _form(ids, category_id=ids["salary"])
    del data["category"]

    r = client.post(f"/transactions/{txn_id}", data=data, headers=ON_LEDGER)

    assert r.status_code == 200
    assert _row(db, txn_id)[1] == ids["salary"]


def test_missing_fields_give_a_human_422_and_write_nothing(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)
    before = _row(db, txn_id)

    r = client.post(f"/transactions/{txn_id}", data={}, headers=FROM_DIALOG)

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["HX-Retarget"] == "#modal-root"
    summary = _html.all_text(r.text, entries.summary)
    assert "Category : pick a category" in summary
    assert _html.count(r.text, entries.edit_dialog) == 1
    assert _row(db, txn_id) == before
    assert _ops(db, txn_id) == ["create"]


def test_a_bad_amount_marks_the_hero_and_keeps_the_posted_values(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)
    before = _row(db, txn_id)

    r = client.post(
        f"/transactions/{txn_id}",
        data=_form(ids, amount="0", description="typed"),
        headers=FROM_DIALOG,
    )

    assert r.status_code == 422
    hero_amount = _html.resolve_one(r.text, entries.edit_amount)
    assert hero_amount.get("aria-invalid") == "true"
    assert hero_amount.get("value") == "0"
    assert _html.resolve_one(r.text, entries.category_option("Groceries")).has_attr("checked")
    assert ledger.control(r.text, entries.field_note).get("value") == "typed"
    assert _html.count(r.text, entries.edit_hero_error) == 1
    assert _row(db, txn_id) == before


def test_a_bad_date_names_the_field_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)
    before = _row(db, txn_id)

    r = client.post(
        f"/transactions/{txn_id}", data=_form(ids, operation_date="nope"), headers=FROM_DIALOG
    )

    assert r.status_code == 422
    assert "Date : invalid date" in _html.all_text(r.text, entries.summary)
    assert _row(db, txn_id) == before


def test_a_transit_edit_needs_a_destination_and_keeps_the_stored_one(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["move"], 2193, dest=ids["pln2"])
    same = client.post(
        f"/transactions/{txn_id}",
        data=_form(ids, category=ids["move"], dest_account_id=ids["pln"]),
        headers=FROM_DIALOG,
    )
    assert same.status_code == 422
    assert _row(db, txn_id)[5] == ids["pln2"]

    moved = client.post(
        f"/transactions/{txn_id}",
        data=_form(ids, category=ids["move"], dest_account_id=ids["eur"], amount="21.93"),
        headers=ON_LEDGER,
    )
    assert moved.status_code == 422
    assert _row(db, txn_id)[5] == ids["pln2"]

    ok = client.post(
        f"/transactions/{txn_id}",
        data=_form(ids, category=ids["move"], amount="30.00"),
        headers=ON_LEDGER,
    )
    assert ok.status_code == 200
    assert _row(db, txn_id)[0] == 3000
    assert _row(db, txn_id)[5] == ids["pln2"]


def test_a_transit_edit_to_a_new_destination_is_stored(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    other = accounts_repo.create(db, USER_ID, NewAccount(name="Third", currency="PLN"))
    txn_id = _txn(db, ids["pln"], ids["move"], 2193, dest=ids["pln2"])

    r = client.post(
        f"/transactions/{txn_id}",
        data=_form(ids, category=ids["move"], dest_account_id=other.id),
        headers=ON_LEDGER,
    )

    assert r.status_code == 200
    assert _row(db, txn_id)[5] == other.id
    assert _ops(db, txn_id) == ["create", "update"]


def test_delete_offers_undo_and_restore_brings_the_row_back(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    txn_id = _txn(db, ids["pln"], ids["groc"], 3550)

    deleted = client.post(f"/transactions/{txn_id}/delete", headers=HX)

    assert deleted.status_code == 200
    assert deleted.headers["HX-Reswap"] == "delete"
    assert json.loads(deleted.headers["HX-Trigger"])["ledger-stale"] is True
    assert _html.text_of(deleted.text, rd_shell.toast_root) == "transaction deleted undo"
    undo = _html.resolve_one(deleted.text, entries.toast_undo)
    undo_form = undo.find_parent("form")
    assert undo_form is not None
    assert undo_form.get("hx-post") == f"/transactions/{txn_id}/restore"
    gone = db.execute("SELECT deleted_at IS NOT NULL FROM transactions WHERE id = ?", (txn_id,))
    assert gone.fetchone()[0] == 1

    restored = client.post(f"/transactions/{txn_id}/restore", headers=HX)

    assert restored.status_code == 200
    assert restored.text == ""
    back = db.execute("SELECT deleted_at IS NULL FROM transactions WHERE id = ?", (txn_id,))
    assert back.fetchone()[0] == 1
    assert _ops(db, txn_id)[0] == "create"
    assert len(_ops(db, txn_id)) == 3
