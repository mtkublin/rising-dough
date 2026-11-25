"""T-UR10a: the Planned, Recurring and Recently deleted views on the new shell (ADR-0107, ADR-0152).

Exact values: signed amounts, the status text of ``planned_status``, the override delta of
``override_delta``, the row menus that open the dialogs, and a restored row with its audit rows.
"""

from __future__ import annotations

import json
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
from tests.ui_map.locator import by_id, role

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


def _ops(db: sqlite3.Connection, entity: str, entity_id: int) -> list[str]:
    return [
        r[0]
        for r in db.execute(
            "SELECT operation FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id",
            (entity, entity_id),
        )
    ]


def _other_users_deleted_rows(db: sqlite3.Connection) -> tuple[int, int]:
    """A second user with a soft-deleted planned row and an archived category."""
    other = 2
    db.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (other,))
    acc = accounts_repo.create(db, other, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(db, other, NewCategory(name="Secret", direction=Direction.EXPENSE))
    planned = planned_repo.create(
        db,
        other,
        NewPlannedTransaction(
            operation_date=clock.today_local(Settings()),
            category_id=cat.id,
            account_id=acc.id,
            amount=9999,
            description="theirs-planned",
        ),
    )
    planned_repo.soft_delete(db, other, planned.id)
    gone = categories_repo.create(db, other, NewCategory(name="Gone", direction=Direction.INCOME))
    categories_repo.soft_delete(db, other, gone.id)
    return planned.id, gone.id


def test_recently_deleted_restore_brings_the_row_back_with_its_audit(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    other_planned, other_cat = _other_users_deleted_rows(db)
    other_planned_ops = _ops(db, "planned_transaction", other_planned)
    assert other_planned_ops == ["create", "delete"]
    pid = ids["later"]
    client.post(f"/planned/{pid}/delete", headers=_HTMX)
    listed = client.get("/ledger/recently-deleted").text
    row = _html.text_of(listed, ledger.deleted_row("planned", pid))
    assert "car" in row and "\N{MINUS SIGN}2,239.80 PLN" in row
    assert "deleted" in row
    # The second user's deleted rows never show for user 1.
    assert not _html.exists(listed, ledger.deleted_row("planned", other_planned))
    assert not _html.exists(listed, ledger.deleted_row("category", other_cat))
    assert "theirs-planned" not in listed and "Secret" not in listed
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
    assert _ops(db, "planned_transaction", pid) == ["create", "delete", "undelete"]
    # The other user's row stays deleted and its audit trail is untouched; user 1 cannot restore it.
    assert _ops(db, "planned_transaction", other_planned) == other_planned_ops
    assert client.post(f"/planned/{other_planned}/restore", headers=_HTMX).status_code == 404
    still = planned_repo.find_by_id(db, 2, other_planned, include_deleted=True)
    assert still is not None and still.deleted_at is not None
    assert _ops(db, "planned_transaction", other_planned) == other_planned_ops


def test_recently_deleted_category_restore(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    _, other_cat = _other_users_deleted_rows(db)
    other_ops = _ops(db, "category", other_cat)
    cid = ids["inc"]
    assert client.post(f"/categories/{cid}/archive", headers=_HTMX).status_code == 204
    listed = client.get("/ledger/recently-deleted").text
    row = _html.text_of(listed, ledger.deleted_row("category", cid))
    assert "Refund" in row and "\N{UPWARDS ARROW} income" in row
    assert not _html.exists(listed, ledger.deleted_row("category", other_cat))
    assert "Gone" not in listed
    assert client.post(f"/categories/{cid}/restore", headers=_HTMX).status_code == 204
    assert not _html.exists(
        client.get("/ledger/recently-deleted").text, ledger.deleted_row("category", cid)
    )
    found = categories_repo.find_by_id(db, USER_ID, cid)
    assert found is not None and found.deleted_at is None
    ops = _ops(db, "category", cid)
    assert ops[-2:] == ["delete", "undelete"] and ops[0] == "create"
    assert _ops(db, "category", other_cat) == other_ops
    other = categories_repo.find_by_id(db, 2, other_cat, include_deleted=True)
    assert other is not None and other.deleted_at is not None


_TABS = role("navigation", "Ledger view")
_DELETED_PANEL = by_id("deleted-panel")


def test_table_refetch_carries_hero_and_tab_counts_out_of_band(
    client: TestClient, ids: dict[str, int]
) -> None:
    """After a rule delete the refetched table swaps the hero figure and the tab counts too."""
    query = "view=recurring&date_from=2000-01-01&date_to=2099-12-31"
    before = client.get(f"/ledger/table?{query}", headers=_HTMX).text
    assert _html.text_of(before, ledger.schedule_hero).startswith(
        "recurring \N{MIDDLE DOT} per month \N{MINUS SIGN}1,200.50 PLN out in 0.00"
    )
    assert "recurring 1" in _html.text_of(before, _TABS)
    assert _html.resolve_one(before, ledger.schedule_hero).get("hx-swap-oob") == "true"
    assert _html.resolve_one(before, _TABS).get("hx-swap-oob") == "true"

    assert client.post(f"/recurring/{ids['rule']}/deactivate", headers=_HTMX).status_code == 200
    after = client.get(f"/ledger/table?{query}", headers=_HTMX).text
    hero = _html.text_of(after, ledger.schedule_hero)
    assert "1,200.50" not in hero and "0.00 PLN out" in hero
    assert "recurring 0" in _html.text_of(after, _TABS)
    assert not _html.exists(after, ledger.recurring_row(ids["rule"]))


def test_full_page_hero_is_not_out_of_band(client: TestClient, ids: dict[str, int]) -> None:
    html = client.get("/ledger?view=planned").text
    assert _html.resolve_one(html, ledger.schedule_hero).get("hx-swap-oob") is None
    assert _html.resolve_one(html, _TABS).get("hx-swap-oob") is None


def test_deleted_panel_refetch_updates_rows_counts_and_empty_state(
    client: TestClient, ids: dict[str, int]
) -> None:
    pid = ids["later"]
    client.post(f"/planned/{pid}/delete", headers=_HTMX)
    page = client.get("/ledger/recently-deleted").text
    panel = _html.resolve_one(page, _DELETED_PANEL)
    assert panel.get("hx-get") == "/ledger/recently-deleted/panel"
    assert "ledger-stale" in str(panel.get("hx-trigger"))
    assert "settings-categories-stale" in str(panel.get("hx-trigger"))
    assert _html.resolve_one(page, ledger.restore("planned", pid)).get("hx-swap") == "none"
    assert "Planned \N{MIDDLE DOT} 1" in _html.text_of(page, _DELETED_PANEL)

    restored = client.post(f"/planned/{pid}/restore", headers=_HTMX)
    assert json.loads(restored.headers["HX-Trigger"]) == {
        "forecast-stale": True,
        "ledger-stale": True,
        "toast": {"variant": "success", "message": "Planned entry restored"},
    }
    fragment = client.get("/ledger/recently-deleted/panel", headers=_HTMX).text
    assert not _html.exists(fragment, ledger.deleted_row("planned", pid))
    text = _html.text_of(fragment, _DELETED_PANEL)
    assert "Planned \N{MIDDLE DOT} 0" in text and "Nothing deleted." in text


def test_transaction_restore_toasts(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    created = client.post(
        "/transactions",
        data={
            "operation_date": "2026-11-01",
            "amount": "10",
            "account_id": str(ids["acc"]),
            "category_id": str(ids["exp"]),
        },
        headers=_HTMX,
    )
    assert created.status_code in (200, 201, 204)
    tid = db.execute("SELECT id FROM transactions ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert client.post(f"/transactions/{tid}/delete", headers=_HTMX).status_code == 200
    resp = client.post(f"/transactions/{tid}/restore", headers=_HTMX)
    assert json.loads(resp.headers["HX-Trigger"])["toast"] == {
        "variant": "success",
        "message": "Transaction restored",
    }
    assert _ops(db, "transaction", tid) == ["create", "delete", "undelete"]
