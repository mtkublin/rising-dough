"""Plan · budget "set budget" action (T-UR55, F4.6c, operator review R4).

An unbudgeted row shows a "set budget" button that opens the dialog on "every month (default)";
a budgeted row keeps the menu with "edit budget". Saving writes the default tier, audited.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import AuditOperation, Direction
from budget_planner.repositories import (
    audit as audit_repo,
    budgets as budgets_repo,
    categories as categories_repo,
)
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import audit_total
from tests.ui_map import _html, plan_budget, plan_year, rd_dialogs

pytest_plugins = ("tests.contract.test_plan_support",)

USER_ID = 1
URL = "/plan?tab=budget&year=2026&month=3"
HX = {"HX-Request": "true"}
SCOPES = ["this month only", "every march", "every month (default)"]
SET_DIALOG = plan_year.set_dialog("Groceries")


@pytest.fixture
def unbudgeted(client: TestClient, account_id: int, cat_id: int) -> int:
    """Groceries has a spend (so its row is listed) but no budget."""
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-03-10",
            "category_id": str(cat_id),
            "account_id": str(account_id),
            "amount": "40",
            "description": "shop",
        },
    )
    assert r.status_code < 400
    return cat_id


def test_unbudgeted_row_has_set_budget_button_opening_the_default_scope(
    client: TestClient, unbudgeted: int
) -> None:
    page = client.get(URL).text

    button = _html.resolve_one(page, plan_budget.set_budget_button("Groceries"))
    target = f"/budget/rules/{unbudgeted}/overrides/new?year=2026&month=3&tier=default"
    assert button.get("hx-get") == target
    assert button.get("hx-target") == "#modal-root"
    assert _html.count(page, plan_budget.edit_budget_item("Groceries")) == 0

    dialog = client.get(target, headers=HX).text
    assert _html.count(dialog, SET_DIALOG) == 1
    checked = [
        t
        for t in SCOPES
        if _html.resolve_one(dialog, plan_year.tier(SET_DIALOG, t)).has_attr("checked")
    ]
    assert checked == ["every month (default)"]


def test_budgeted_row_menu_says_edit_budget_and_has_no_set_budget_button(
    client: TestClient, cat_id: int
) -> None:
    assert client.post(f"/budget/defaults/{cat_id}", data={"amount": "500"}).status_code == 200

    page = client.get(URL).text

    assert _html.count(page, plan_budget.edit_budget_item("Groceries")) == 1
    assert _html.count(page, plan_budget.set_budget_button("Groceries")) == 0
    dialog = client.get(f"/budget/rules/{cat_id}/overrides/new?year=2026&month=3", headers=HX).text
    assert _html.count(dialog, plan_year.dialog("Groceries", "Mar 2026")) == 1


def test_hint_shows_only_while_no_category_has_a_budget(
    client: TestClient, unbudgeted: int
) -> None:
    before = client.get(URL).text
    assert "set budget" in _html.text_of(before, plan_budget.no_budget_hint)

    assert client.post(f"/budget/defaults/{unbudgeted}", data={"amount": "500"}).status_code == 200

    assert _html.count(client.get(URL).text, plan_budget.no_budget_hint) == 0


def test_set_budget_default_scope_writes_the_default_and_audits_it(
    client: TestClient, db: sqlite3.Connection, unbudgeted: int
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    theirs = categories_repo.create(
        db, other, NewCategory(name="Theirs", direction=Direction.EXPENSE)
    )
    before = audit_total(db)

    r = client.post(
        f"/budget/rules/{unbudgeted}/overrides",
        data={"year": "2026", "month": "3", "tier": "default", "amount": "450.50"},
    )

    assert r.status_code == 200
    row = budgets_repo.get_default(db, USER_ID, unbudgeted)
    assert row is not None
    assert row.amount == 45_050
    entries = audit_repo.list_entries(db, USER_ID, "budget_default", row.id)
    assert [str(e.operation) for e in entries] == [AuditOperation.CREATE]
    assert audit_total(db) == before + 1
    assert budgets_repo.get_default(db, other, theirs.id) is None
    assert budgets_repo.get_one_off(db, USER_ID, unbudgeted, 2026, 3) is None


def test_set_budget_with_an_empty_amount_shows_the_field_error_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection, unbudgeted: int
) -> None:
    before = audit_total(db)

    r = client.post(
        f"/budget/rules/{unbudgeted}/overrides",
        data={"year": "2026", "month": "3", "tier": "default", "amount": ""},
    )

    assert r.status_code == 422
    assert _html.count(r.text, rd_dialogs.field_error(SET_DIALOG, "amount")) == 1
    assert budgets_repo.get_default(db, USER_ID, unbudgeted) is None
    assert audit_total(db) == before


# --- edit budget opens on the row's current tier (BUDUX, R4/R5) ----------------------


def _edit_link(page: str, name: str) -> str:
    link = _html.resolve_one(page, plan_budget.edit_budget_item(name))
    href = link.get("href")
    assert href == link.get("hx-get")
    assert isinstance(href, str)
    return href


@pytest.fixture
def tiered(client: TestClient, db: sqlite3.Connection, cat_id: int) -> dict[str, int]:
    """Groceries: default 500; Car: recurring March 300 over a default; Fun: one-off March 80."""
    ids = {"Groceries": cat_id}
    for name in ("Car", "Fun"):
        ids[name] = categories_repo.create(
            db, USER_ID, NewCategory(name=name, direction=Direction.EXPENSE)
        ).id
    for cid in ids.values():
        assert client.post(f"/budget/defaults/{cid}", data={"amount": "500"}).status_code == 200
    for name, tier, amount in (("Car", "recurring", "300"), ("Fun", "one-off", "80")):
        r = client.post(
            f"/budget/rules/{ids[name]}/overrides",
            data={"year": "2026", "month": "3", "tier": tier, "amount": amount},
        )
        assert r.status_code == 200
    return ids


@pytest.mark.parametrize(
    ("name", "tier", "checked"),
    [
        ("Groceries", "default", "every month (default)"),
        ("Car", "recurring", "every march"),
        ("Fun", "one-off", "this month only"),
    ],
)
def test_edit_budget_opens_on_the_rows_current_tier(
    client: TestClient, tiered: dict[str, int], name: str, tier: str, checked: str
) -> None:
    href = _edit_link(client.get(URL).text, name)
    assert href == f"/budget/rules/{tiered[name]}/overrides/new?year=2026&month=3&tier={tier}"

    dialog = client.get(href, headers=HX).text

    dlg = plan_year.dialog(name, "Mar 2026")
    got = [
        t for t in SCOPES if _html.resolve_one(dialog, plan_year.tier(dlg, t)).has_attr("checked")
    ]
    assert got == [checked]


def test_saving_the_default_row_dialog_unchanged_updates_the_default_only(
    client: TestClient, db: sqlite3.Connection, tiered: dict[str, int]
) -> None:
    gid = tiered["Groceries"]
    dialog = client.get(_edit_link(client.get(URL).text, "Groceries"), headers=HX).text
    dlg = plan_year.dialog("Groceries", "Mar 2026")
    amount = _html.resolve_one(dialog, plan_year.amount(dlg)).get("value")
    assert amount == "500.00"
    before = audit_total(db)

    r = client.post(
        f"/budget/rules/{gid}/overrides",
        data={"year": "2026", "month": "3", "tier": "default", "amount": amount},
    )

    assert r.status_code == 200
    row = budgets_repo.get_default(db, USER_ID, gid)
    assert row is not None
    assert row.amount == 50_000
    assert budgets_repo.get_one_off(db, USER_ID, gid, 2026, 3) is None
    assert budgets_repo.get_recurring(db, USER_ID, gid, 3) is None
    entries = audit_repo.list_entries(db, USER_ID, "budget_default", row.id)
    assert [str(e.operation) for e in entries] == [AuditOperation.CREATE, AuditOperation.UPDATE]
    assert audit_total(db) == before + 1
