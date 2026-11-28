"""Ledger Actual view on the new shell: rows, day nets, states, filters (T-UR09, ADR-0107)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    fx as fx_repo,
    transactions as transactions_repo,
)
from tests.auth_support import seed_login_user
from tests.ui_map import _html, ledger, rd_shell
from tests.ui_map.locator import by_id, label, role

pytestmark = pytest.mark.integration

USER_ID = 1
OTHER_ID = 2
MINUS = "\N{MINUS SIGN}"
TRANSIT = "\N{RIGHTWARDS ARROW OVER LEFTWARDS ARROW}"
DAY = date(2026, 11, 2)  # a Monday


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _txn(
    db: sqlite3.Connection,
    account_id: int,
    category_id: int,
    amount: int,
    description: str,
    *,
    day: date = DAY,
    dest: int | None = None,
    user: int = USER_ID,
) -> int:
    return transactions_repo.create(
        db,
        user,
        NewTransaction(
            operation_date=day,
            category_id=category_id,
            account_id=account_id,
            amount=amount,
            description=description,
            dest_account_id=dest,
        ),
    ).id


def _cells(html: str, txn_id: int) -> list[str]:
    """Description, category and amount cells of a row (the select and menu cells dropped)."""
    cells = _html.resolve(html, ledger.row_cells(txn_id))
    return [" ".join(c.get_text(" ").split()) for c in cells][1:4]


def _world(db: sqlite3.Connection) -> dict[str, int]:
    main = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    euro = accounts_repo.create(db, USER_ID, NewAccount(name="Euro", currency="EUR"))
    food = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE, color="#ff9f43")
    )
    pay = categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    transit = categories_repo.find_by_name(db, USER_ID, "Transit")
    recon = categories_repo.find_by_name(db, USER_ID, "Reconciliation")
    assert transit is not None
    assert recon is not None
    fx_repo.upsert_rate(db, NewFxRate(date=DAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4")))
    return {
        "main": main.id,
        "euro": euro.id,
        "food": food.id,
        "pay": pay.id,
        "transit": transit.id,
        "recon": recon.id,
    }


def test_rows_show_signed_amounts_in_the_account_currency(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    spend = _txn(db, w["main"], w["food"], 1234, "Milk")
    income = _txn(db, w["main"], w["pay"], 500000, "Payday")
    moved = _txn(db, w["main"], w["transit"], 2193, "Move", dest=w["euro"])
    fix = _txn(db, w["main"], w["recon"], -1472, "Fix")
    euro = _txn(db, w["euro"], w["food"], 2500, "Pizza")
    r = client.get("/ledger")
    assert r.status_code == 200
    assert _cells(r.text, spend) == ["Milk Main", "Groceries", f"{MINUS}12.34 PLN"]
    assert _cells(r.text, income) == ["Payday Main", "Salary", "+5,000.00 PLN"]
    assert _cells(r.text, moved) == ["Move Main → Euro", "Transit", f"{TRANSIT} 21.93 PLN"]
    assert _cells(r.text, fix) == ["Fix Main", "Reconciliation", f"{MINUS}14.72 PLN"]
    assert _cells(r.text, euro) == ["Pizza Euro", "Groceries", f"{MINUS}25.00 EUR"]


def test_day_heading_nets_in_the_base_currency(client: TestClient, db: sqlite3.Connection) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1000, "Milk")
    _txn(db, w["euro"], w["food"], 2500, "Pizza")  # 25.00 EUR at 4.0 = 100.00 PLN
    _txn(db, w["main"], w["pay"], 50000, "Payday", day=date(2026, 11, 1))
    r = client.get("/ledger")
    assert _html.text_of(r.text, ledger.day_head("MON 02 NOV")) == f"MON 02 NOV NET {MINUS}110.00"
    assert _html.text_of(r.text, ledger.day_head("SUN 01 NOV")) == "SUN 01 NOV NET +500.00"
    # newest day first
    assert ledger.day_heads(r.text) == [f"MON 02 NOV NET {MINUS}110.00", "SUN 01 NOV NET +500.00"]


def test_rows_of_another_user_are_absent(client: TestClient, db: sqlite3.Connection) -> None:
    w = _world(db)
    mine = _txn(db, w["main"], w["food"], 1000, "Mine")
    seed_login_user(db, user_id=OTHER_ID, email="two@example.test")
    acc = accounts_repo.create(db, OTHER_ID, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(
        db, OTHER_ID, NewCategory(name="Secret", direction=Direction.EXPENSE)
    )
    theirs = _txn(db, acc.id, cat.id, 999, "Theirs", user=OTHER_ID)
    r = client.get("/ledger")
    assert _html.exists(r.text, ledger.row(mine))
    assert not _html.exists(r.text, ledger.row(theirs))
    assert "Theirs" not in _html.page_text(r.text)
    assert "Secret" not in _html.page_text(r.text)


def test_hero_is_the_period_spend_and_tabs_carry_counts(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1234, "Milk")
    r = client.get("/ledger")
    assert _html.text_of(r.text, ledger.heading) == "spent this period"
    assert _html.text_of(r.text, ledger.view_tab("actual")) == "actual 1"


def test_row_menu_edits_in_the_dialog_root_and_deletes_with_confirm(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    tid = _txn(db, w["main"], w["food"], 1234, "Milk")
    r = client.get("/ledger")
    assert _html.exists(r.text, ledger.row_menu(tid))
    items = ledger.menu_items(r.text, tid)
    assert list(items) == ["edit", "delete", "cancel"]
    edit = items["edit"]
    assert edit.get("hx-get") == f"/transactions/{tid}/edit"
    assert edit.get("hx-target") == "#modal-root"
    delete = items["delete"]
    assert delete.get("hx-post") == f"/transactions/{tid}/delete"
    assert delete.get("hx-target") == f"#txn-{tid}"
    assert delete.get("hx-confirm") == "Delete this transaction?"


def test_bulk_bar_is_hidden_until_selection_and_its_actions_are_disabled(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    tid = _txn(db, w["main"], w["food"], 1234, "Milk")
    r = client.get("/ledger")
    bar = _html.resolve_one(r.text, ledger.bulk_bar)
    assert bar.has_attr("hidden")
    assert [b.get_text(strip=True) for b in bar.find_all("button") if b.has_attr("disabled")] == [
        "change category",
        "delete",
    ]
    box = _html.resolve_one(r.text, ledger.select_box(tid))
    assert box.get("name") == "ids"
    assert box.get("value") == str(tid)
    assert box.get("aria-label") == f"Select Milk, {MINUS}12.34 PLN"


def test_custom_category_hue_gets_its_rule_and_a_preset_its_name(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1234, "Milk")
    odd = categories_repo.create(
        db, USER_ID, NewCategory(name="Odd", direction=Direction.EXPENSE, color="#123456")
    )
    _txn(db, w["main"], odd.id, 100, "Thing")
    r = client.get("/ledger")
    chips = ledger.chips(r.text)
    assert chips == {"Groceries": "orange", "Odd": "c-123456"}
    assert ledger.color_rules(r.text).startswith(
        '[data-color="c-123456"]{--cat:#123456;--cat-edge:'
    )


def test_first_run_with_no_entries(client: TestClient, db: sqlite3.Connection) -> None:
    _world(db)
    r = client.get("/ledger")
    assert "No entries yet." in _html.page_text(r.text)
    assert _html.exists(r.text, ledger.table_container)
    new_entry = _html.resolve_one(
        r.text, role("link", "[ new entry ]").inside(ledger.table_container)
    )
    assert new_entry.get("href") == "/add?when=happened&dialog=1"


def test_no_matches_names_the_filters_and_clears_them(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1234, "Milk")
    r = client.get(
        "/ledger/table",
        params={
            "q": "pizza",
            "category_id": w["food"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        },
    )
    assert r.status_code == 200
    text = _html.page_text(r.text)
    dot, dash = "\N{MIDDLE DOT}", "\N{EN DASH}"
    quoted = "\N{LEFT DOUBLE QUOTATION MARK}pizza\N{RIGHT DOUBLE QUOTATION MARK}"
    summary = f"Groceries {dot} 01/01/2026 {dash} 31/01/2026 {dot} {quoted}"
    assert f"Nothing matches these filters. {summary}" in text
    clear = _html.resolve_one(r.text, role("link", "clear filters"))
    assert clear.get("href") == "/ledger"
    assert ledger.txn_row_ids(r.text) == []


def test_filter_bar_marks_the_active_filters(client: TestClient, db: sqlite3.Connection) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1234, "Milk")
    r = client.get(
        "/ledger",
        params={
            "category_id": w["food"],
            "account_id": w["euro"],
            "direction": "transit",
            "q": "x",
        },
    )
    selected = {
        "category": _html.resolve_one(r.text, label("category").inside(ledger.filters_form)),
        "account": _html.resolve_one(r.text, label("account").inside(ledger.filters_form)),
        "direction": _html.resolve_one(r.text, label("direction").inside(ledger.filters_form)),
    }
    assert {
        k: [o.get_text(strip=True) for o in v.find_all("option", selected=True)]
        for k, v in selected.items()
    } == {"category": ["Groceries"], "account": ["Euro"], "direction": ["transfer"]}
    assert _html.resolve_one(r.text, ledger.filter_search).get("value") == "x"
    assert _html.resolve_one(r.text, ledger.filters_form).get("data-state") == "expanded"
    form = _html.resolve_one(r.text, ledger.filters_form)
    assert form.get("hx-get") == "/ledger/table"
    assert form.get("hx-target") == "#ledger-table"


def test_pagination_links_carry_the_filters(client: TestClient, db: sqlite3.Connection) -> None:
    w = _world(db)
    for n in range(3):
        _txn(db, w["main"], w["food"], 100 + n, f"Item {n}", day=date(2026, 11, 1 + n))
    first = client.get("/ledger", params={"page_size": 2, "category_id": w["food"]})
    older = _html.resolve_one(first.text, ledger.older_button)
    assert older.get("href") == f"/ledger?view=actual&category_id={w['food']}&page_size=2&page=2"
    assert not _html.exists(first.text, ledger.newer_button)
    second = client.get("/ledger", params={"page_size": 2, "category_id": w["food"], "page": 2})
    assert ledger.txn_row_ids(second.text) == [f"txn-{_first_id(db)}"]
    newer = _html.resolve_one(second.text, ledger.newer_button)
    assert newer.get("href") == f"/ledger?view=actual&category_id={w['food']}&page_size=2&page=1"
    assert not _html.exists(second.text, ledger.older_button)
    deleted = _html.resolve_one(second.text, ledger.recently_deleted_link)
    assert deleted.get("href") == "/ledger/recently-deleted"


def _first_id(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT MIN(id) FROM transactions").fetchone()[0])


def test_long_list_renders_every_row_of_the_page_in_date_order(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    ids = [
        _txn(db, w["main"], w["food"], 100 + n, f"Item {n}", day=date(2026, 10, 1 + n))
        for n in range(30)
    ]
    r = client.get("/ledger")
    assert ledger.txn_row_ids(r.text) == [f"txn-{i}" for i in reversed(ids)]
    assert len(ledger.day_heads(r.text)) == len(ids)
    assert _html.count(r.text, by_id("ledger-table")) == 1


def test_new_entry_button_opens_the_dialog_in_place(client: TestClient) -> None:
    r = client.get("/ledger")
    button = _html.resolve_one(r.text, rd_shell.new_entry)
    assert button.get("hx-get") == "/add?when=happened&dialog=1"
    assert button.get("hx-target") == "#modal-root"
    # no script: the shell page opens the dialog
    assert button.get("href") == "/add?when=happened&dialog=1"


def test_filter_response_refreshes_the_export_links_and_pushes_the_url(
    client: TestClient, db: sqlite3.Connection
) -> None:
    w = _world(db)
    _txn(db, w["main"], w["food"], 1234, "Milk")
    params: dict[str, str | int] = {
        "category_id": w["food"],
        "q": "milk",
        "date_from": "2026-11-01",
    }
    query = f"date_from=2026-11-01&category_id={w['food']}&q=milk"
    r = client.get(
        "/ledger/table",
        params=params,
        headers={"HX-Request": "true", "HX-Trigger": "ledger-filters"},
    )
    csv = f"/transactions/export?{query}&format=csv"
    assert ledger.export_hrefs(r.text) == {
        "export as csv": csv,
        "export as parquet": f"/transactions/export?{query}&format=parquet",
    }
    assert r.headers["HX-Push-Url"] == f"/ledger?view=actual&{query}"
    # a refetch by ledger-stale keeps the URL as it is
    stale = client.get("/ledger/table", params=params, headers={"HX-Trigger": "ledger-table"})
    assert "HX-Push-Url" not in stale.headers
    # the full page renders the menu once, in place
    page = client.get("/ledger", params=params)
    assert ledger.export_hrefs(page.text)["export as csv"] == csv
