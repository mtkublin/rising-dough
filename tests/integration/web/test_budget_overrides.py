"""Budget override dialogs: open, save, 422 and remove with exact rows and audit (T-UR11).

World: Groceries default 500.00 plus a one-off 321.00 for March 2026 and a recurring 700.00 for
June; Rent has only a default. The dialog is one form for the three tiers; the scope radio picks
the stored row. Every write is audited, every failure writes nothing.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import AuditOperation, Direction
from budget_planner.repositories import (
    audit as audit_repo,
    budgets as budgets_repo,
    categories as categories_repo,
)
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import audit_total, hx_events
from tests.ui_map import _html, plan_year
from tests.ui_map.locator import Locator, by_id

pytest_plugins = ("tests.contract.test_plan_support",)

USER_ID = 1
HX = {"HX-Request": "true"}
FLASH = by_id("flash-region")
SUMMARY = by_id("error-summary")
MARCH = "year=2026&month=3"
POST_FORM = {"year": "2026", "month": "3"}


@pytest.fixture
def groceries(db: sqlite3.Connection, cat_id: int) -> int:
    budgets_repo.set_default(db, USER_ID, NewBudgetDefault(category_id=cat_id, amount=50_000))
    budgets_repo.set_one_off(
        db, USER_ID, NewBudgetOneOffOverride(category_id=cat_id, year=2026, month=3, amount=32_100)
    )
    budgets_repo.set_recurring(
        db, USER_ID, NewBudgetRecurringOverride(category_id=cat_id, month=6, amount=70_000)
    )
    return cat_id


@pytest.fixture
def rent(db: sqlite3.Connection) -> int:
    made = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(db, USER_ID, NewBudgetDefault(category_id=made.id, amount=120_050))
    return made.id


def _open(client: TestClient, category: int, query: str) -> str:
    r = client.get(f"/budget/rules/{category}/overrides/new?{query}", headers=HX)
    assert r.status_code == 200
    assert r.headers["hx-retarget"] == "#modal-root"
    return r.text


def _checked(page: str, dialog: Locator, labels: list[str]) -> list[str]:
    return [
        t for t in labels if _html.resolve_one(page, plan_year.tier(dialog, t)).has_attr("checked")
    ]


def _entries(db: sqlite3.Connection, entity: str, entity_id: int) -> list[str]:
    return [str(e.operation) for e in audit_repo.list_entries(db, USER_ID, entity, entity_id)]


# --- open ------------------------------------------------------------------------


def test_month_dialog_shows_the_stored_one_off_and_the_default(
    client: TestClient, groceries: int
) -> None:
    page = _open(client, groceries, f"{MARCH}&tier=one-off")

    dlg = plan_year.dialog("Groceries", "Mar 2026")
    assert _html.count(page, dlg) == 1
    assert _html.resolve_one(page, plan_year.amount(dlg)).get("value") == "321.00"
    assert "default 500.00" in _html.all_text(page, dlg)
    labels = ["this month only", "every march", "new default"]
    assert _checked(page, dlg, labels) == ["this month only"]
    assert _html.count(page, plan_year.remove_override(dlg)) == 1
    assert _html.count(page, plan_year.save(dlg)) == 1


def test_scope_opens_on_the_requested_tier_with_its_own_stored_amount(
    client: TestClient, groceries: int
) -> None:
    page = _open(client, groceries, "year=2026&month=6&tier=recurring")

    dlg = plan_year.dialog("Groceries", "Jun 2026")
    assert _checked(page, dlg, ["this month only", "every june", "new default"]) == ["every june"]
    assert _html.resolve_one(page, plan_year.amount(dlg)).get("value") == "700.00"
    default_page = _open(client, groceries, f"{MARCH}&tier=default")
    default_dlg = plan_year.dialog("Groceries", "Mar 2026")
    assert _html.resolve_one(default_page, plan_year.amount(default_dlg)).get("value") == "500.00"
    assert _checked(
        default_page, default_dlg, ["this month only", "every march", "new default"]
    ) == ["new default"]


def test_month_without_override_prefills_the_resolved_amount_and_offers_no_remove(
    client: TestClient, groceries: int
) -> None:
    page = _open(client, groceries, "year=2026&month=9&tier=one-off")

    dlg = plan_year.dialog("Groceries", "Sep 2026")
    assert _html.resolve_one(page, plan_year.amount(dlg)).get("value") == "500.00"
    assert _html.count(page, plan_year.remove_override(dlg)) == 0


def test_unknown_or_foreign_category_is_404(client: TestClient, db: sqlite3.Connection) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    theirs = categories_repo.create(
        db, other, NewCategory(name="Theirs", direction=Direction.EXPENSE)
    )

    assert client.get(f"/budget/rules/{theirs.id}/overrides/new?{MARCH}").status_code == 404
    before = audit_total(db)
    r = client.post(
        f"/budget/rules/{theirs.id}/overrides", data={**POST_FORM, "tier": "default", "amount": "1"}
    )
    assert r.status_code == 404
    assert budgets_repo.get_default(db, other, theirs.id) is None
    assert audit_total(db) == before


# --- save --------------------------------------------------------------------------


def test_this_month_only_creates_a_one_off_and_audits_it(
    client: TestClient, db: sqlite3.Connection, rent: int
) -> None:
    r = client.post(
        f"/budget/rules/{rent}/overrides",
        data={**POST_FORM, "tier": "one-off", "amount": "1500.25"},
    )

    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    row = budgets_repo.get_one_off(db, USER_ID, rent, 2026, 3)
    assert row is not None
    assert row.amount == 150_025
    assert _entries(db, "budget_one_off_override", row.id) == [AuditOperation.CREATE]
    flash = _html.all_text(r.text, FLASH)
    assert flash.endswith("Rent budget saved")
    default = budgets_repo.get_default(db, USER_ID, rent)
    assert default is not None
    assert default.amount == 120_050


def test_saving_again_updates_the_same_row_and_audits_the_update(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    before = budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3)
    assert before is not None

    r = client.post(
        f"/budget/rules/{groceries}/overrides",
        data={**POST_FORM, "tier": "one-off", "amount": "99.99"},
    )

    assert r.status_code == 200
    after = budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3)
    assert after is not None
    assert (after.id, after.amount) == (before.id, 9_999)
    assert _entries(db, "budget_one_off_override", before.id) == [
        AuditOperation.CREATE,
        AuditOperation.UPDATE,
    ]
    assert len(budgets_repo.list_one_off(db, USER_ID)) == 1


def test_every_month_writes_a_recurring_override_for_that_month_only(
    client: TestClient, db: sqlite3.Connection, rent: int
) -> None:
    r = client.post(
        f"/budget/rules/{rent}/overrides", data={**POST_FORM, "tier": "recurring", "amount": "1300"}
    )

    assert r.status_code == 200
    row = budgets_repo.get_recurring(db, USER_ID, rent, 3)
    assert row is not None
    assert row.amount == 130_000
    assert budgets_repo.get_recurring(db, USER_ID, rent, 4) is None
    assert budgets_repo.get_one_off(db, USER_ID, rent, 2026, 3) is None
    assert _entries(db, "budget_recurring_override", row.id) == [AuditOperation.CREATE]


def test_new_default_replaces_the_default(
    client: TestClient, db: sqlite3.Connection, rent: int
) -> None:
    default = budgets_repo.get_default(db, USER_ID, rent)
    assert default is not None

    r = client.post(
        f"/budget/rules/{rent}/overrides",
        data={**POST_FORM, "tier": "default", "amount": "1250.00"},
    )

    assert r.status_code == 200
    after = budgets_repo.get_default(db, USER_ID, rent)
    assert after is not None
    assert (after.id, after.amount) == (default.id, 125_000)
    assert _entries(db, "budget_default", default.id) == [
        AuditOperation.CREATE,
        AuditOperation.UPDATE,
    ]


# --- 422 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        ({"tier": "one-off", "amount": "nope"}, "amount", "enter an amount of 0 or more"),
        ({"tier": "one-off", "amount": "-5"}, "amount", "enter an amount of 0 or more"),
        ({"tier": "monthly", "amount": "5"}, "tier", "choose where the override applies"),
        ({"tier": "recurring", "amount": "5", "month": "13"}, "month", "pick a month from 1 to 12"),
    ],
)
def test_invalid_save_is_a_422_with_the_summary_and_writes_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    rent: int,
    case: tuple[dict[str, str], str, str],
) -> None:
    form, field, message = case
    before = audit_total(db)

    r = client.post(f"/budget/rules/{rent}/overrides", data={**POST_FORM, **form}, headers=HX)

    assert r.status_code == 422
    assert "HX-Trigger" not in r.headers
    assert r.headers["hx-retarget"] == "#modal-root"
    if field == "amount":
        expected = {"field-amount-error": f"▲ {message}"}
    else:  # the dialog has no tier/month field: the shell shows the dialog-level line
        expected = {f"dialog-error-{field}": f"▲ {field.title()}: {message}"}
    assert _html.error_lines(r.text) == expected
    assert audit_total(db) == before
    assert budgets_repo.list_one_off(db, USER_ID) == []
    assert budgets_repo.list_recurring(db, USER_ID) == []
    default = budgets_repo.get_default(db, USER_ID, rent)
    assert default is not None
    assert default.amount == 120_050


def test_invalid_amount_is_shown_again_in_the_dialog(client: TestClient, rent: int) -> None:
    r = client.post(
        f"/budget/rules/{rent}/overrides",
        data={**POST_FORM, "tier": "recurring", "amount": "12x"},
        headers=HX,
    )

    dlg = plan_year.dialog("Rent", "Mar 2026")
    amount = _html.resolve_one(r.text, plan_year.amount(dlg))
    assert (amount.get("value"), amount.get("aria-invalid")) == ("12x", "true")
    assert _html.resolve_one(r.text, plan_year.tier(dlg, "every march")).has_attr("checked")


# --- remove ------------------------------------------------------------------------


def test_remove_confirm_names_the_amount_the_month_falls_back_to(
    client: TestClient, groceries: int
) -> None:
    page = _open(client, groceries, f"{MARCH}&tier=one-off&remove=1")

    dlg = plan_year.remove_dialog()
    assert _html.count(page, dlg) == 1
    text = _html.all_text(page, dlg)
    assert "Groceries · Mar 2026 goes back to the default 500.00 PLN." in text
    assert _html.count(page, plan_year.confirm_remove(dlg)) == 1
    assert _html.count(page, plan_year.keep(dlg)) == 1


def test_remove_confirm_falls_back_to_the_recurring_override_when_one_exists(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    budgets_repo.set_recurring(
        db, USER_ID, NewBudgetRecurringOverride(category_id=groceries, month=3, amount=45_000)
    )

    page = _open(client, groceries, f"{MARCH}&tier=one-off&remove=1")

    assert "Groceries · Mar 2026 goes back to the recurring override 450.00 PLN." in _html.all_text(
        page, plan_year.remove_dialog()
    )


def test_remove_deletes_the_one_off_audits_it_and_leaves_the_rest(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    one_off = budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3)
    assert one_off is not None

    r = client.post(
        f"/budget/rules/{groceries}/overrides",
        data={**POST_FORM, "tier": "one-off", "remove": "1"},
    )

    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3) is None
    assert _entries(db, "budget_one_off_override", one_off.id) == [
        AuditOperation.CREATE,
        AuditOperation.DELETE,
    ]
    deleted = db.execute(
        "SELECT amount, deleted_at IS NOT NULL FROM budget_one_off_overrides WHERE id = ?",
        (one_off.id,),
    ).fetchone()
    assert tuple(deleted) == (32_100, 1)
    recurring = budgets_repo.get_recurring(db, USER_ID, groceries, 6)
    assert recurring is not None
    assert recurring.amount == 70_000
    default = budgets_repo.get_default(db, USER_ID, groceries)
    assert default is not None
    assert default.amount == 50_000
    assert "Groceries override removed" in _html.all_text(r.text, FLASH)


def test_remove_deletes_the_recurring_override(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    recurring = budgets_repo.get_recurring(db, USER_ID, groceries, 6)
    assert recurring is not None

    r = client.post(
        f"/budget/rules/{groceries}/overrides",
        data={"year": "2026", "month": "6", "tier": "recurring", "remove": "1"},
    )

    assert r.status_code == 200
    assert budgets_repo.get_recurring(db, USER_ID, groceries, 6) is None
    assert _entries(db, "budget_recurring_override", recurring.id) == [
        AuditOperation.CREATE,
        AuditOperation.DELETE,
    ]
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3) is not None


@pytest.mark.parametrize(
    ("form", "line"),
    [
        (
            {"tier": "default", "year": "2026", "month": "3"},
            ("dialog-error-tier", "▲ Tier: choose where the override applies"),
        ),
        (
            {"tier": "one-off", "year": "2026", "month": "13"},
            ("dialog-error-month", "▲ Month: pick a month from 1 to 12"),
        ),
        (
            {"tier": "one-off", "year": "x", "month": "3"},
            ("dialog-error-year", "▲ Year: enter a year"),
        ),
    ],
)
def test_invalid_remove_is_a_422_and_removes_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    groceries: int,
    form: dict[str, str],
    line: tuple[str, str],
) -> None:
    before = audit_total(db)

    r = client.post(
        f"/budget/rules/{groceries}/overrides", data={**form, "remove": "1"}, headers=HX
    )

    assert r.status_code == 422
    assert "HX-Trigger" not in r.headers
    assert _html.error_lines(r.text) == dict([line])
    assert audit_total(db) == before
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 3) is not None
    assert budgets_repo.get_default(db, USER_ID, groceries) is not None
