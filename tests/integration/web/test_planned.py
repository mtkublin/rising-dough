"""T-034 planned router."""

from __future__ import annotations

import io
import json
import re
import sqlite3
from collections.abc import Iterator
from datetime import date

import pyarrow.parquet as pq
import pytest
from bs4 import Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import sign_glyph
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from tests.ui_map import (
    _html,
    edit_dialogs,
    entries,
    errors,
    ledger,
    rd_fragments,
    rd_shell as shell,
)
from tests.ui_map.locator import by_id, role

USER_ID = 1
_HTMX = {"HX-Request": "true"}
_FROM_DIALOG = {"HX-Request": "true", "HX-Target": "modal-root"}


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _planned_state(db: sqlite3.Connection) -> list[tuple[object, ...]]:
    """Every planned row (deleted included) as plain tuples, for before/after equality."""
    return [
        tuple(r)
        for r in db.execute(
            "SELECT id, operation_date, category_id, account_id, amount, description, "
            "deleted_at IS NOT NULL, promoted_to_txn_id FROM planned_transactions ORDER BY id"
        )
    ]


def _txn_count(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=50000,
                description="rent",
            ),
        )
        return {"acc": acc.id, "cat": cat.id, "pl": pl.id}
    finally:
        conn.close()


def test_table_fragment(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get("/planned/table")
    assert _html.exists(r.text, ledger.view_table("planned"))
    # no page chrome: the only heading is the hero that refreshes out of band with the rows
    assert _html.count(r.text, ledger.heading) == 1
    assert _html.exists(r.text, ledger.heading.inside(ledger.schedule_hero))


def test_new_form(client: TestClient) -> None:
    r = client.get("/add?when=planned&dialog=1", headers=_HTMX)
    assert r.status_code == 200
    assert _html.exists(r.text, entries.tab_planned)
    due = _html.resolve_one(r.text, entries.field_due)
    assert (due.get("name"), due.get("type")) == ("operation_date", "date")


def test_create(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "123.45",
            "description": "x",
        },
    )
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {
        "forecast-stale": True,
        "ledger-stale": True,
        "today-stale": True,
    }
    assert _html.text_of(r.text, shell.modal_root) == ""
    assert _html.all_text(r.text, errors.status) == "● Planned entry saved"
    row = db.execute(
        "SELECT amount, description FROM planned_transactions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (row[0], row[1]) == (12345, "x")


def test_create_bad_amount(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _planned_state(db)
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "-1",
        },
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ Enter an amount above 0.00",
    }
    assert _planned_state(db) == before


def test_create_bad_date(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _planned_state(db)
    r = client.post(
        "/planned",
        data={
            "operation_date": "bad",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "1",
        },
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-operation_date-error": "▲ invalid date",
    }
    assert _planned_state(db) == before


def test_create_unknown_account(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _planned_state(db)
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": 9999,
            "amount": "10",
        },
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-account_id-error": "▲ unknown account",
    }
    assert _planned_state(db) == before


def _edit_dialog(text: str) -> Tag:
    return _html.resolve_one(text, edit_dialogs.planned_dialog("Rent"))


def _hero_part(text: str, css_class: str) -> Tag:
    """One element of the dialog hero (sign, amount input, currency), by the shell's class."""
    hero = _edit_dialog(text).find("div", class_="rd-dialog__hero")
    assert isinstance(hero, Tag)
    part = hero.find(class_=css_class)
    assert isinstance(part, Tag)
    return part


def _audit_rows(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def _other_users_planned(db: sqlite3.Connection) -> int:
    """A planned item of a second user (their own account and category)."""
    db.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    acc = accounts_repo.create(db, 2, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(db, 2, NewCategory(name="Rent", direction=Direction.EXPENSE))
    pl = planned_repo.create(
        db,
        2,
        NewPlannedTransaction(
            operation_date=date(2026, 10, 15),
            category_id=cat.id,
            account_id=acc.id,
            amount=1,
            description="theirs",
        ),
    )
    return pl.id


def test_edit_opens_the_dialog_with_the_stored_values(
    client: TestClient, ctx: dict[str, int]
) -> None:
    r = client.get(f"/planned/{ctx['pl']}/edit", headers=_HTMX)
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    dialog = _edit_dialog(r.text)
    form = dialog.find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == (
        f"/planned/{ctx['pl']}",
        "#modal-root",
    )
    scope = edit_dialogs.planned_dialog("Rent")
    amount = _html.resolve_one(r.text, edit_dialogs.hero_amount(scope))
    assert (amount.get("name"), amount.get("value")) == ("amount", "500.00")
    assert _hero_part(r.text, "rd-dialog__sign").get_text() == sign_glyph(True)
    assert _hero_part(r.text, "rd-dialog__cur").get_text() == "PLN"
    due = _html.resolve_one(r.text, edit_dialogs.field_due(scope))
    note = _html.resolve_one(r.text, edit_dialogs.field_note(scope))
    assert (due.get("name"), due.get("value")) == ("operation_date", "2026-10-15")
    assert (note.get("name"), note.get("value")) == ("description", "rent")
    chips = [
        (c.get("value"), c.has_attr("checked"))
        for c in _html.resolve(r.text, rd_fragments.category_recent_radios)
    ]
    assert chips[0] == (str(ctx["cat"]), True)
    assert [checked for _, checked in chips].count(True) == 1
    account = _html.resolve_one(r.text, edit_dialogs.field_account(scope))
    selected = account.find("option", selected=True)
    assert selected is not None
    assert selected.get("value") == str(ctx["acc"])


def test_edit_404(client: TestClient) -> None:
    r = client.get("/planned/9999/edit", headers=_HTMX)
    assert r.status_code == 404
    assert r.text == "planned: not found"


def test_edit_of_another_users_item_is_404(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    theirs = _other_users_planned(db)
    assert client.get(f"/planned/{theirs}/edit", headers=_HTMX).status_code == 404
    before = _planned_state(db)
    r = client.post(f"/planned/{theirs}", data=_planned_data(ctx), headers=_FROM_DIALOG)
    assert r.status_code == 404
    assert _planned_state(db) == before


def test_hero_refresh_follows_the_form_not_the_stored_item(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    income = categories_repo.create(
        db, USER_ID, NewCategory(name="Bonus", direction=Direction.INCOME)
    )
    eur = accounts_repo.create(db, USER_ID, NewAccount(name="Euro", currency="EUR"))
    r = client.get(
        f"/planned/{ctx['pl']}/edit?hero=1&category={income.id}&account_id={eur.id}&amount=12.50",
        headers=_HTMX,
    )
    assert r.status_code == 200
    assert "HX-Retarget" not in r.headers
    assert _hero_part(r.text, "rd-dialog__sign").get_text() == sign_glyph(False)
    assert _hero_part(r.text, "rd-dialog__cur").get_text() == "EUR"
    assert _hero_part(r.text, "rd-dialog__amount").get("value") == "12.50"


def test_update(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "2026-10-20",
            "category": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "77.77",
            "description": "moved",
        },
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"forecast-stale": True, "ledger-stale": True}
    # the dialog closes (modal-root emptied out of band) and the flash says what happened
    modal_root = _html.resolve_one(r.text, by_id("modal-root"))
    assert (modal_root.get("hx-swap-oob"), modal_root.get_text(strip=True)) == ("innerHTML", "")
    assert "Planned entry saved" in _html.all_text(r.text, errors.status)
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert (stored.amount, stored.operation_date, stored.description) == (
        7_777,
        date(2026, 10, 20),
        "moved",
    )
    ops = [
        row[0]
        for row in db.execute(
            "SELECT operation FROM audit_log WHERE entity_type = 'planned_transaction' "
            "AND entity_id = ? ORDER BY id",
            (ctx["pl"],),
        )
    ]
    assert ops == ["create", "update"]


def test_update_accepts_the_old_category_id_name(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    data = {**_planned_data(ctx), "amount": "5"}
    assert client.post(f"/planned/{ctx['pl']}", data=data).status_code == 200
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert stored.amount == 500


def test_update_404(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _planned_state(db)
    r = client.post(
        "/planned/9999",
        data={
            "operation_date": "2026-10-20",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "10",
        },
    )
    assert r.status_code == 404
    assert r.text == "not found"
    assert _planned_state(db) == before


def test_update_invalid(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _planned_state(db)
    audit_before = _audit_rows(db)
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "bad",
            "category": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "-1",
            "description": "kept",
        },
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ Enter an amount above 0.00",
        "field-operation_date-error": "▲ invalid date",
    }
    scope = edit_dialogs.planned_dialog("Rent")
    # the dialog comes back with what was posted, nothing stored
    assert _html.resolve_one(r.text, edit_dialogs.field_due(scope)).get("value") == "bad"
    assert _html.resolve_one(r.text, edit_dialogs.field_note(scope)).get("value") == "kept"
    assert _html.resolve_one(r.text, edit_dialogs.hero_amount(scope)).get("value") == "-1"
    assert _planned_state(db) == before
    assert _audit_rows(db) == audit_before


def test_update_with_nothing_posted_names_every_missing_field(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _planned_state(db)
    r = client.post(f"/planned/{ctx['pl']}", data={}, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "catpick-edit-planned-error": "▲ Pick a category",
        "field-account_id-error": "▲ unknown account",
        "field-operation_date-error": "▲ invalid date",
    }
    assert "Pick a category" in _html.all_text(r.text, edit_dialogs.planned_dialog("Rent"))
    assert _planned_state(db) == before


def test_delete(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(f"/planned/{ctx['pl']}/delete")
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"forecast-stale": True, "ledger-stale": True}
    assert r.headers["HX-Reswap"] == "delete"
    undo = _html.resolve_one(r.text, role("button", "undo", exact=True))
    form = undo.find_parent("form")
    assert form is not None
    assert form.get("action") == f"/planned/{ctx['pl']}/restore"
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"], include_deleted=True)
    assert stored is not None
    assert stored.deleted_at is not None
    ops = [
        row[0]
        for row in db.execute(
            "SELECT operation FROM audit_log WHERE entity_type = 'planned_transaction' "
            "AND entity_id = ? ORDER BY id",
            (ctx["pl"],),
        )
    ]
    assert ops == ["create", "delete"]


def test_undo_restores_the_deleted_item(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    client.post(f"/planned/{ctx['pl']}/delete")
    r = client.post(f"/planned/{ctx['pl']}/restore")
    assert r.status_code == 200
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert stored.deleted_at is None


def test_promote_form(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/planned/{ctx['pl']}/promote", headers=_HTMX)
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.promote)


def test_promote_form_404(client: TestClient) -> None:
    r = client.get("/planned/9999/promote")
    assert r.status_code == 404
    assert r.text == "planned: not found"


def test_promote_submit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500", "description": "r"},
    )
    assert r.status_code == 200
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {
        "balance-stale": True,
        "forecast-stale": True,
        "ledger-stale": True,
        "today-stale": True,
    }
    assert _html.text_of(r.text, by_id("flash-region")).endswith("Planned entry promoted")


def test_promote_submit_invalid(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _planned_state(db)
    txns = _txn_count(db)
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "bad", "amount": "-1"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ Enter an amount above 0.00",
        "field-operation_date-error": "▲ invalid date",
    }
    assert _planned_state(db) == before
    assert _txn_count(db) == txns


def test_promote_submit_404(client: TestClient, db: sqlite3.Connection) -> None:
    txns = _txn_count(db)
    r = client.post(
        "/planned/9999/promote",
        data={"operation_date": "2026-10-20", "amount": "1"},
    )
    assert r.status_code == 404
    assert r.text == "not found"
    assert _txn_count(db) == txns


def test_promote_already_promoted(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500"},
    )
    txns = _txn_count(db)
    assert txns == 1
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500"},
    )
    assert r.status_code == 422
    assert "This planned transaction was already promoted." in _html.all_text(r.text, errors.alert)
    assert "promotion: 1" not in _html.all_text(r.text, errors.alert)
    assert _txn_count(db) == txns


def test_export_csv(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get("/planned/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


def test_export_parquet(client: TestClient, ctx: dict[str, int]) -> None:
    # Explicit date window — ctx creates a planned on 2026-10-15 and the
    # default window is "current calendar month" (services.planned.
    # _default_window), which drops the fixture row once today rolls past
    # Oct 2026.
    r = client.get("/planned/export?format=parquet&date_from=2026-10-01&date_to=2026-10-31")
    assert r.status_code == 200
    tbl = pq.read_table(io.BytesIO(r.content))
    assert tbl.num_rows >= 1


def _planned_data(ctx: dict[str, int]) -> dict[str, str | int]:
    return {
        "operation_date": "2026-11-01",
        "category_id": ctx["cat"],
        "account_id": ctx["acc"],
        "amount": "12.34",
    }


def test_create_off_ledger_refreshes_page_without_swap(
    client: TestClient, ctx: dict[str, int]
) -> None:
    # T-D142: the form is opened from Today etc.; no table to swap into.
    r = client.post(
        "/planned",
        data=_planned_data(ctx),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/today"},
    )
    assert r.status_code == 200
    assert "HX-Reswap" not in r.headers
    assert "HX-Refresh" not in r.headers
    assert "today-stale" in r.headers["HX-Trigger"]
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_create_on_ledger_does_not_refresh_page(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned",
        data=_planned_data(ctx),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=planned"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_new_form_posts_into_the_modal_root_not_the_planned_table(client: TestClient) -> None:
    r = client.get("/add?when=planned&dialog=1", headers=_HTMX)
    form = _html.resolve_one(r.text, entries.dialog).find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == ("/planned", "#modal-root")


_ON_TODAY = {"HX-Request": "true", "HX-Current-URL": "http://testserver/today"}
_ON_LEDGER = {"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=planned"}


def test_update_closes_the_dialog_from_any_page(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    """Today and the ledger listen for ledger-stale: no reload, the dialog empties itself."""
    url = f"/planned/{ctx['pl']}"
    for headers in (_ON_TODAY, _ON_LEDGER):
        r = client.post(url, data=_planned_data(ctx), headers=headers)
        assert r.status_code == 200
        assert "HX-Refresh" not in r.headers
        assert json.loads(r.headers["HX-Trigger"]) == {
            "forecast-stale": True,
            "ledger-stale": True,
        }
        modal_root = _html.resolve_one(r.text, by_id("modal-root"))
        assert modal_root.get_text(strip=True) == ""
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert stored.amount == 1_234


def test_update_invalid_amount_rerenders_the_dialog_in_place(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    data = {**_planned_data(ctx), "amount": "0"}
    r = client.post(f"/planned/{ctx['pl']}", data=data, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert "HX-Trigger" not in r.headers
    assert _html.exists(r.text, edit_dialogs.planned_dialog("Rent"))
    hero = _html.resolve_one(r.text, edit_dialogs.hero_amount(edit_dialogs.planned_dialog("Rent")))
    assert hero.get("aria-invalid") == "true"
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert stored.amount == 50_000


def test_promote_dialog_prefills_the_planned_values(
    client: TestClient, ctx: dict[str, int]
) -> None:
    r = client.get(f"/planned/{ctx['pl']}/promote", headers=_HTMX)
    assert r.headers["HX-Retarget"] == "#modal-root"
    dialog = _html.resolve_one(r.text, role("dialog", re.compile("^promote to actual")))
    form = dialog.find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == (
        f"/planned/{ctx['pl']}/promote",
        "#modal-root",
    )
    amount = _html.resolve_one(r.text, entries.promote_amount)
    date_field = _html.resolve_one(r.text, entries.promote_date)
    note = _html.resolve_one(r.text, entries.promote_note)
    assert (amount.get("name"), amount.get("value")) == ("amount", "500.00")
    assert (date_field.get("name"), date_field.get("value")) == ("operation_date", "2026-10-15")
    assert (note.get("name"), note.get("value")) == ("description", "rent")


def test_promote_off_ledger_refreshes_page(client: TestClient, ctx: dict[str, int]) -> None:
    form = {"operation_date": "2026-10-15", "amount": "500.00"}
    off = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_TODAY)
    assert off.status_code == 200
    assert "HX-Reswap" not in off.headers
    assert "HX-Refresh" not in off.headers
    assert "today-stale" in off.headers["HX-Trigger"]
    assert "ledger-stale" in off.headers["HX-Trigger"]


def test_promote_on_ledger_does_not_refresh_page(client: TestClient, ctx: dict[str, int]) -> None:
    form = {"operation_date": "2026-10-15", "amount": "500.00"}
    on = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_LEDGER)
    assert on.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in on.headers


def test_promote_invalid_amount_rerenders_dialog(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _planned_state(db)
    form = {"operation_date": "2026-10-15", "amount": "0"}
    r = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_LEDGER)
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ Enter an amount above 0.00",
    }
    assert _planned_state(db) == before


def test_promote_get_is_always_the_dialog(client: TestClient, ctx: dict[str, int]) -> None:
    """T-UR24: no ``?dialog=`` switch, no slide-over; the inline form route is gone."""
    r = client.get(f"/planned/{ctx['pl']}/promote", headers=_HTMX)
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.exists(r.text, role("dialog", re.compile("^promote to actual")))
    assert client.get(f"/planned/{ctx['pl']}/promote/inline", headers=_HTMX).status_code == 404
