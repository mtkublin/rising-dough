"""T-UR10a: the Planned, Recurring and Recently deleted views on the new shell (ADR-0107, ADR-0152).

Exact values: signed amounts, the status text of ``planned_status``, the override delta of
``override_delta``, the row menus that open the dialogs, and a restored row with its audit rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
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


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    exp = categories_repo.create(db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE))
    inc = categories_repo.create(
        db, USER_ID, NewCategory(name="Refund", direction=Direction.INCOME)
    )
    today = clock.today_local(Settings())
    out: dict[str, int] = {"acc": acc.id, "exp": exp.id, "inc": inc.id}
    for key, cat, day, amount, text in (
        ("late", exp, today - timedelta(days=3), 41200, "annual insurance"),
        ("today", inc, today, 112045, "tax refund"),
        ("later", exp, today + timedelta(days=45), 223980, "car"),
    ):
        out[key] = planned_repo.create(
            db,
            USER_ID,
            NewPlannedTransaction(
                operation_date=day,
                category_id=cat.id,
                account_id=acc.id,
                amount=amount,
                description=text,
            ),
        ).id
    out["rule"] = recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=exp.id,
            account_id=acc.id,
            default_amount=120050,
            default_description="rent",
        ),
    ).id
    return out


def test_planned_rows_show_signed_amount_and_status(
    client: TestClient, ids: dict[str, int]
) -> None:
    html = client.get("/ledger?view=planned").text
    late = _html.text_of(html, ledger.planned_row(ids["late"]))
    assert "annual insurance" in late
    assert "\N{MINUS SIGN}412.00 PLN" in late
    assert "\N{BLACK UP-POINTING TRIANGLE} overdue 3 days" in late
    due_today = _html.text_of(html, ledger.planned_row(ids["today"]))
    assert "+1,120.45 PLN" in due_today
    assert "\N{BLACK CIRCLE} due today" in due_today
    later = _html.text_of(html, ledger.planned_row(ids["later"]))
    assert "\N{MINUS SIGN}2,239.80 PLN" in later
    assert "in 45 days" in later
    hero = _html.text_of(html, ledger.schedule_hero)
    assert hero == (
        "planned \N{MINUS SIGN}1,531.35 PLN net 3 items \N{MIDDLE DOT} 1 overdue "
        "\N{MIDDLE DOT} 1 due today"
    )


def test_planned_row_menu_opens_the_dialogs(client: TestClient, ids: dict[str, int]) -> None:
    html = client.get("/ledger?view=planned").text
    pid = ids["later"]
    actions = ledger.menu_actions(html, ledger.planned_row(pid))
    assert {k: (v.get("hx-get") or v.get("hx-post")) for k, v in actions.items()} == {
        "promote": f"/planned/{pid}/promote?dialog=1",
        "edit": f"/planned/{pid}/edit",
        "delete": f"/planned/{pid}/delete",
        "cancel": None,
    }
    assert actions["edit"].get("hx-target") == "#modal-root"
    assert actions["delete"].get("hx-confirm") == "Delete this planned entry?"
    promote = _html.resolve_one(html, ledger.planned_promote(pid))
    assert (promote.get("hx-get"), promote.get("hx-target")) == (
        f"/planned/{pid}/promote?dialog=1",
        "#modal-root",
    )


def test_recurring_row_override_detail_shows_amount_and_delta(
    client: TestClient, ids: dict[str, int]
) -> None:
    rule = ids["rule"]
    assert (
        client.post(
            f"/recurring/{rule}/overrides", data={"year": 2026, "month": 2, "amount": "1000.00"}
        ).status_code
        == 200
    )
    html = client.get("/ledger?view=recurring&date_from=2000-01-01&date_to=2099-12-31").text
    row = _html.text_of(html, ledger.recurring_row(rule))
    assert "rent" in row and "\N{MINUS SIGN}1,200.50 PLN" in row
    assert "1 override" in row
    detail = _html.text_of(html, ledger.recurring_expand(rule))
    # 1,000.00 against the 1,200.50 rule amount: 200.50 lower.
    assert "Feb 2026 1,000.00 PLN \N{MINUS SIGN}200.50" in detail
    remove = _html.resolve_one(html, ledger.recurring_expand(rule)).find(
        "a", attrs={"hx-get": True}
    )
    assert remove is not None
    assert remove.get("hx-get") in {
        f"/recurring/{rule}/overrides/new",
        f"/recurring/{rule}/overrides/new?occurrence_date=2026-02-01&remove=1",
    }


def test_recurring_row_menu_opens_the_dialogs(client: TestClient, ids: dict[str, int]) -> None:
    rule = ids["rule"]
    html = client.get("/ledger?view=recurring&date_from=2000-01-01&date_to=2099-12-31").text
    actions = ledger.menu_actions(html, ledger.recurring_row(rule))
    assert {k: (v.get("hx-get") or v.get("hx-post")) for k, v in actions.items()} == {
        "promote": f"/recurring/{rule}/promote?dialog=1",
        "override": f"/recurring/{rule}/overrides/new",
        "skip next": f"/recurring/{rule}/skip-next",
        "edit": f"/recurring/{rule}/edit",
        "delete": f"/recurring/{rule}/deactivate",
        "cancel": None,
    }
    assert actions["skip next"].get("hx-swap") == "none"
    assert actions["delete"].get("hx-swap") == "none"
    hero = _html.text_of(html, ledger.schedule_hero)
    assert hero.startswith(
        "recurring \N{MIDDLE DOT} per month \N{MINUS SIGN}1,200.50 PLN out in 0.00"
    )


def test_recently_deleted_restore_brings_the_row_back_with_its_audit(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    pid = ids["later"]
    client.post(f"/planned/{pid}/delete", headers=_HTMX)
    listed = client.get("/ledger/recently-deleted").text
    row = _html.text_of(listed, ledger.deleted_row("planned", pid))
    assert "car" in row and "\N{MINUS SIGN}2,239.80 PLN" in row
    assert "deleted" in row
    assert not _html.exists(client.get("/ledger?view=planned").text, ledger.planned_row(pid))
    restore = _html.resolve_one(listed, ledger.restore("planned", pid))
    assert restore.get("hx-post") == f"/planned/{pid}/restore"

    resp = client.post(f"/planned/{pid}/restore", headers=_HTMX)
    assert resp.status_code == 200
    assert "ledger-stale" in resp.headers["HX-Trigger"]
    assert _html.exists(client.get("/ledger?view=planned").text, ledger.planned_row(pid))
    assert not _html.exists(
        client.get("/ledger/recently-deleted").text, ledger.deleted_row("planned", pid)
    )
    ops = [
        r[0]
        for r in db.execute(
            "SELECT operation FROM audit_log WHERE entity_type = 'planned_transaction' "
            "AND entity_id = ? ORDER BY id",
            (pid,),
        )
    ]
    assert ops == ["create", "delete", "undelete"]


def test_recently_deleted_category_restore(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    cid = ids["inc"]
    assert client.post(f"/categories/{cid}/archive", headers=_HTMX).status_code == 204
    row = _html.text_of(
        client.get("/ledger/recently-deleted").text, ledger.deleted_row("category", cid)
    )
    assert "Refund" in row and "\N{UPWARDS ARROW} income" in row
    assert client.post(f"/categories/{cid}/restore", headers=_HTMX).status_code == 204
    assert not _html.exists(
        client.get("/ledger/recently-deleted").text, ledger.deleted_row("category", cid)
    )
    found = categories_repo.find_by_id(db, USER_ID, cid)
    assert found is not None and found.deleted_at is None
