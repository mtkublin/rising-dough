"""T-034 planned router."""

from __future__ import annotations

import io
import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from tests.ui_map import _html, ledger

USER_ID = 1
_HTMX = {"HX-Request": "true"}


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
    assert not _html.exists(r.text, ledger.heading)  # fragment: no page chrome


def test_new_form(client: TestClient) -> None:
    r = client.get("/planned/new", headers=_HTMX)
    assert r.status_code == 200
    assert ledger.controls(r.text, ledger.field_date.inside(ledger.planned_form))


def test_create(client: TestClient, ctx: dict[str, int]) -> None:
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
    assert "forecast-stale" in r.headers["HX-Trigger"]


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
    assert "<strong>amount:</strong> amount must be positive" in r.text
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
    assert "<strong>operation_date:</strong> invalid date" in r.text
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
    assert "<strong>account_id:</strong> unknown account" in r.text
    assert _planned_state(db) == before


def test_edit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/planned/{ctx['pl']}/edit", headers=_HTMX)
    assert r.status_code == 200
    assert ledger.control(r.text, ledger.field_amount).get("value") == "500.00"


def test_edit_404(client: TestClient) -> None:
    r = client.get("/planned/9999/edit")
    assert r.status_code == 404
    assert "<strong>planned:</strong> not found" in r.text


def test_update(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "2026-10-20",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "77.77",
        },
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]
    stored = planned_repo.find_by_id(db, USER_ID, ctx["pl"])
    assert stored is not None
    assert stored.amount == 7_777
    assert stored.operation_date == date(2026, 10, 20)


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
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "bad",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "-1",
        },
    )
    assert r.status_code == 422
    assert "<strong>operation_date:</strong> invalid date" in r.text
    assert "<strong>amount:</strong> amount must be positive" in r.text
    assert _planned_state(db) == before


def test_delete(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/planned/{ctx['pl']}/delete")
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_delete_404(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _planned_state(db)
    r = client.post("/planned/9999/delete")
    assert r.status_code == 404
    assert r.text == "not found"
    assert _planned_state(db) == before


def test_promote_form(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/planned/{ctx['pl']}/promote", headers=_HTMX)
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.promote)


def test_promote_form_404(client: TestClient) -> None:
    r = client.get("/planned/9999/promote")
    assert r.status_code == 404
    assert "<strong>planned:</strong> not found" in r.text


def test_promote_submit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500", "description": "r"},
    )
    assert r.status_code == 200
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}


def test_promote_submit_invalid(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _planned_state(db)
    txns = _txn_count(db)
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "bad", "amount": "-1"},
    )
    assert r.status_code == 422
    assert "<strong>operation_date:</strong> invalid date" in r.text
    assert "<strong>amount:</strong> amount must be positive" in r.text
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
    assert "This planned transaction was already promoted." in r.text
    assert "<strong>promotion:</strong> 1" not in r.text
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
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
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


def test_new_form_targets_itself_not_planned_table(client: TestClient) -> None:
    r = client.get("/planned/new", headers=_HTMX)
    assert _html.resolve_one(r.text, ledger.planned_form).get("hx-target") == "#planned-form"


_ON_TODAY = {"HX-Request": "true", "HX-Current-URL": "http://testserver/today"}
_ON_LEDGER = {"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=planned"}


def test_edit_form_targets_itself_and_closes_on_success(
    client: TestClient, ctx: dict[str, int]
) -> None:
    r = client.get(f"/planned/{ctx['pl']}/edit", headers=_HTMX)
    form = _html.resolve_one(r.text, ledger.planned_form)
    assert form.get("hx-target") == "#planned-form"
    assert form.has_attr("data-close-overlay-on-success")


def test_update_off_ledger_refreshes_and_on_ledger_does_not(
    client: TestClient, ctx: dict[str, int]
) -> None:
    url = f"/planned/{ctx['pl']}"
    off = client.post(url, data=_planned_data(ctx), headers=_ON_TODAY)
    assert off.status_code == 200
    assert off.headers["HX-Reswap"] == "none"
    assert off.headers["HX-Refresh"] == "true"
    assert "ledger-stale" in off.headers["HX-Trigger"]
    on = client.post(url, data=_planned_data(ctx), headers=_ON_LEDGER)
    assert on.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in on.headers


def test_update_invalid_amount_rerenders_form_in_place(
    client: TestClient, ctx: dict[str, int]
) -> None:
    data = {**_planned_data(ctx), "amount": "0"}
    r = client.post(f"/planned/{ctx['pl']}", data=data, headers=_ON_TODAY)
    assert r.status_code == 422
    assert _html.exists(r.text, ledger.planned_form)


def test_promote_modal_is_slide_over_that_closes_on_success(
    client: TestClient, ctx: dict[str, int]
) -> None:
    r = client.get(f"/planned/{ctx['pl']}/promote", headers=_HTMX)
    assert _html.exists(r.text, ledger.slideover)
    form = _html.resolve_one(r.text, ledger.promote).find_parent("form")
    assert form is not None
    assert form.get("hx-target") == "closest .slide-over-root"
    assert form.has_attr("data-close-overlay-on-success")


def test_promote_off_ledger_refreshes_page(client: TestClient, ctx: dict[str, int]) -> None:
    form = {"operation_date": "2026-10-15", "amount": "500.00"}
    off = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_TODAY)
    assert off.status_code == 200
    assert off.headers["HX-Reswap"] == "none"
    assert off.headers["HX-Refresh"] == "true"
    assert "ledger-stale" in off.headers["HX-Trigger"]


def test_promote_on_ledger_does_not_refresh_page(client: TestClient, ctx: dict[str, int]) -> None:
    form = {"operation_date": "2026-10-15", "amount": "500.00"}
    on = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_LEDGER)
    assert on.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in on.headers


def test_promote_invalid_amount_rerenders_modal(client: TestClient, ctx: dict[str, int]) -> None:
    form = {"operation_date": "2026-10-15", "amount": "0"}
    r = client.post(f"/planned/{ctx['pl']}/promote", data=form, headers=_ON_LEDGER)
    assert r.status_code == 422
    assert _html.exists(r.text, ledger.slideover)
