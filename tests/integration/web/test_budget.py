"""T-036 budget router."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import (
    budgets as budgets_repo,
    categories as categories_repo,
)
from tests.ui_map import _html, plan, plan_budget, plan_year
from tests.ui_map.locator import by_id

USER_ID = 1
ERROR_SUMMARY = by_id("error-summary")


@pytest.fixture
def cat_id(_migrated: Settings) -> int:
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        return cat.id
    finally:
        conn.close()


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _budget_rows(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Row counts of (defaults, recurring overrides, one-off overrides), deleted included."""
    return (
        len(budgets_repo.list_defaults(conn, USER_ID, include_deleted=True)),
        len(budgets_repo.list_recurring(conn, USER_ID, include_deleted=True)),
        len(budgets_repo.list_one_off(conn, USER_ID, include_deleted=True)),
    )


def _audit_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def test_set_default(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "500"})
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]
    stored = budgets_repo.get_default(db, USER_ID, cat_id)
    assert stored is not None
    assert stored.amount == 50_000
    assert _budget_rows(db) == (1, 0, 0)
    audit = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = 'budget_default'"
    ).fetchall()
    assert [row["operation"] for row in audit] == ["create"]


def test_set_default_404(client: TestClient, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post("/budget/defaults/9999", data={"amount": "100"})
    assert r.status_code == 404
    assert r.text == "not found"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_set_default_invalid(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "nan"})
    assert r.status_code == 422
    assert r.text == "invalid amount"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_set_default_negative(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "-5"})
    assert r.status_code == 422
    assert r.text == "invalid amount"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_set_one_off(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/budget/one-off/{cat_id}/2026/10", data={"amount": "99"})
    assert r.status_code == 200
    assert r.text == "ok"
    stored = budgets_repo.get_one_off(db, USER_ID, cat_id, 2026, 10)
    assert stored is not None
    assert stored.amount == 9_900
    assert _budget_rows(db) == (0, 0, 1)


def test_set_one_off_404(client: TestClient, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post("/budget/one-off/9999/2026/10", data={"amount": "1"})
    assert r.status_code == 404
    assert r.text == "not found"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_set_one_off_bad_month(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post(f"/budget/one-off/{cat_id}/2026/14", data={"amount": "1"})
    assert r.status_code == 422
    assert r.text == "invalid month"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_set_one_off_bad_amount(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    audit_before = _audit_count(db)
    r = client.post(f"/budget/one-off/{cat_id}/2026/10", data={"amount": "nope"})
    assert r.status_code == 422
    assert r.text == "invalid amount"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


# ---------------------------------------------------------------------------
# T-066 — three-section consolidation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T-113 / ADR-0031 — Rules Override dispatcher + Yearly budget grid
# ---------------------------------------------------------------------------


def test_plan_budget_override_item_targets_its_own_category(
    client: TestClient, cat_id: int
) -> None:
    """T-D49: each row's override item opens that category's form; menu ids are unique."""
    r = client.get("/plan?tab=budget&year=2026&month=10")
    assert r.status_code == 200
    item = _html.resolve_one(r.text, plan_budget.override_item("Groceries"))
    target = f"/budget/rules/{cat_id}/overrides/new?year=2026&month=10"
    assert item.get("href") == target
    assert item.get("hx-get") == target
    assert item.get("hx-target") == "#modal-root"
    menu = _html.resolve_one(r.text, plan_budget.row_menu("Groceries"))
    assert menu.get("id") == f"menu-budget-{cat_id}"
    ids = [t["id"] for t in BeautifulSoup(r.text, "html.parser").find_all(id=True)]
    assert len(ids) == len(set(ids))


def test_override_dialog_is_a_fragment_with_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?year=2026&month=3")
    assert r.status_code == 200
    assert _html.is_fragment(r.text)
    form = _html.form_of(r.text, plan.override_amount)
    assert form.get("hx-post") == f"/budget/rules/{cat_id}/overrides"
    assert form.get("hx-target") == "#modal-root"
    assert _html.exists(r.text, plan.override_cancel)
    assert _html.count(r.text, plan.override_tier) == 3
    assert form.find("script") is None


def test_new_override_form_404_for_unknown_category(client: TestClient) -> None:
    r = client.get("/budget/rules/9999/overrides/new")
    assert r.status_code == 404
    assert r.text == "not found"


def test_override_dialog_submits_tier_month_year_and_amount(
    client: TestClient, cat_id: int
) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?year=2026&month=3")
    assert r.status_code == 200
    form = _html.form_of(r.text, plan.tier_one_off)
    names = {name for name, _ in _html.submitted_fields(form)}
    assert {"tier", "year", "month", "amount"} <= names


def test_create_override_recurring(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "recurring", "month": "6", "amount": "250"},
    )
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_create_override_one_off(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "one-off", "month": "7", "year": "2026", "amount": "99"},
    )
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_create_override_404_for_unknown_category(
    client: TestClient, db: sqlite3.Connection
) -> None:
    audit_before = _audit_count(db)
    r = client.post(
        "/budget/rules/9999/overrides",
        data={"tier": "recurring", "month": "6", "amount": "1"},
    )
    assert r.status_code == 404
    assert r.text == "not found"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_create_override_rejects_bad_tier(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    audit_before = _audit_count(db)
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "monthly", "month": "6", "amount": "1"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "dialog-error-tier": "▲ Tier: choose where the override applies",
    }
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_create_override_rejects_bad_month(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    audit_before = _audit_count(db)
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "recurring", "month": "13", "amount": "1"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "dialog-error-month": "▲ Month: pick a month from 1 to 12",
    }
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_create_override_rejects_bad_amount(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    audit_before = _audit_count(db)
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "recurring", "month": "6", "amount": "nope"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ enter an amount of 0 or more",
    }
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


def test_create_override_one_off_rejects_bad_year(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    audit_before = _audit_count(db)
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "one-off", "month": "7", "year": "bogus", "amount": "1"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "dialog-error-year": "▲ Year: enter a year",
    }
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


# ---------------------------------------------------------------------------
def test_override_dialog_prefills_month_and_year(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?month=3&year=2027")
    soup = BeautifulSoup(r.text, "html.parser")
    month = soup.find("input", {"name": "month"})
    year = soup.find("input", {"name": "year"})
    assert isinstance(month, Tag)
    assert isinstance(year, Tag)
    assert (month.get("value"), year.get("value")) == ("3", "2027")


# ---------------------------------------------------------------------------
# T-UR15a: the old /budget pages redirect to /plan; pins ported to the budget and year tabs
# ---------------------------------------------------------------------------


def test_budget_lands_on_the_plan_budget_tab(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    assert _html.document_title(r.text) == "Plan · budget · Rising Dough"


def test_budget_redirect_keeps_the_month(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=10")
    assert "October 2026" in _html.text_of(r.text, plan_budget.period_trigger)


def test_yearly_redirect_lands_on_the_year_tab_with_stored_amounts(
    client: TestClient, cat_id: int
) -> None:
    """Stored minor units print as major-unit decimals (2233 minor -> 22.33)."""
    client.post(f"/budget/one-off/{cat_id}/2026/7", data={"amount": "22.33"})
    r = client.get("/budget/yearly?year=2026")
    assert _html.document_title(r.text) == "Plan · year · Rising Dough"
    july = _html.resolve_one(r.text, plan_year.cell("Groceries", "July"))
    assert july["aria-label"] == "Groceries, July: 22.33 PLN, one-off override"
