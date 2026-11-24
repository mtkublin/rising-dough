"""T-036 budget router."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, errors, plan, plan_budget
from tests.ui_map.locator import role

USER_ID = 1


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


def test_index(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    assert _html.document_title(r.text).startswith("Budget")


def test_index_with_year_month(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=10")
    assert r.status_code == 200
    assert "2026-10" in _html.document_title(r.text)


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


def test_budget_three_sections(client: TestClient, cat_id: int) -> None:
    """Page exposes the three section anchors in order."""
    r = client.get("/budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    summary = soup.find(id="budget-summary")
    rules = soup.find(id="budget-rules")
    breakdown = soup.find(id="budget-breakdown")
    assert isinstance(summary, Tag)
    assert isinstance(rules, Tag)
    assert isinstance(breakdown, Tag)
    # Visual order matches the section narrative.
    order = [s.get("id") for s in soup.find_all("section") if isinstance(s, Tag)]
    assert (
        order.index("budget-summary")
        < order.index("budget-rules")
        < order.index("budget-breakdown")
    )


def test_budget_month_selector_swaps(client: TestClient, _migrated: Settings) -> None:
    """Changing the ``?month=`` query swaps the per-category planned amounts."""
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        # Set a default so the planned column shows a concrete number.
        budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=cat.id, amount=12345))
    finally:
        conn.close()

    r_oct = client.get("/budget?year=2026&month=10")
    r_nov = client.get("/budget?year=2026&month=11")
    assert r_oct.status_code == 200
    assert r_nov.status_code == 200
    assert "2026-10" in _html.document_title(r_oct.text)
    assert "2026-11" in _html.document_title(r_nov.text)
    # The month selector mentions the queried month inside the one-off column
    # header, so the HTML must differ between the two requests.
    assert r_oct.text != r_nov.text


def test_budget_breakdown_has_three_charts(client: TestClient, cat_id: int) -> None:
    """T-R50 (ADR-0054) — Breakdown moved to /plan?tab=analytics; /budget keeps a
    pointer section so bookmarks still land somewhere, but no Plotly charts render."""
    r = client.get("/budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    breakdown = soup.find(id="budget-breakdown")
    assert isinstance(breakdown, Tag)
    # No more Plotly placeholders; link to the Plan hub instead.
    assert not _html.exists(r.text, plan.chart_image.inside(plan.budget_breakdown))
    assert _html.resolve_one(r.text, plan.breakdown_link)["href"] == "/plan?tab=analytics"


# ---------------------------------------------------------------------------
# T-113 / ADR-0031 — Rules Override dispatcher + Yearly budget grid
# ---------------------------------------------------------------------------


def test_yearly_fragment_renders_for_year(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget/yearly?year=2026")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.yearly_section)
    assert _html.exists(r.text, plan.yearly_row("Groceries"))


def test_rules_section_renders_override_button(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    button = _html.resolve_one(r.text, plan.rules_override_button("Groceries"))
    assert button["hx-get"] == f"/budget/rules/{cat_id}/overrides/new"


def test_rules_default_input_renders_major_decimal(client: TestClient, cat_id: int) -> None:
    """Default budget inline input renders stored minor units as major-unit
    decimal with trailing zeros (e.g. 1550 minor → "15.50"), not the raw int."""
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "15.50"})
    r = client.get("/budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    inp = soup.find("input", {"id": f"rule-default-{cat_id}"})
    assert isinstance(inp, Tag)
    assert inp.get("value") == "15.50"


def test_yearly_cell_renders_major_decimal(client: TestClient, cat_id: int) -> None:
    """Yearly grid cells render stored minor units as major-unit decimals."""
    client.post(f"/budget/one-off/{cat_id}/2026/7", data={"amount": "22.33"})
    r = client.get("/budget/yearly?year=2026")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    inp = soup.find("input", {"id": f"y-{cat_id}-7"})
    assert isinstance(inp, Tag)
    assert inp.get("value") == "22.33"


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


def test_inline_override_form_is_fragment_with_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?inline=1")
    assert r.status_code == 200
    assert _html.is_fragment(r.text)
    form = _html.form_of(r.text, plan.override_amount)
    assert form.has_attr("data-override-inline")
    assert _html.exists(r.text, plan.override_cancel)
    assert form.find("script") is None


def test_slideover_override_form_has_no_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new")
    assert not _html.exists(r.text, plan.override_cancel)


def test_new_override_form_404_for_unknown_category(client: TestClient) -> None:
    r = client.get("/budget/rules/9999/overrides/new")
    assert r.status_code == 404
    assert "category: not found" in _html.all_text(r.text, errors.alert)


def test_new_override_form_returns_slide_over(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new")
    assert r.status_code == 200
    form = _html.form_of(r.text, plan.tier_one_off)
    names = {name for name, _ in _html.submitted_fields(form)}
    assert {"tier", "month", "amount"} <= names


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
    assert r.text == "invalid tier"
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
    assert r.text == "invalid month"
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
    assert r.text == "invalid amount"
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
    assert r.text == "invalid year"
    assert _budget_rows(db) == (0, 0, 0)
    assert _audit_count(db) == audit_before


# ---------------------------------------------------------------------------
# T-120 / ADR-0039 — committed sub-line beneath left-daily-spend hero.
# ---------------------------------------------------------------------------
def test_budget_hero_renders_committed_subline(client: TestClient, cat_id: int) -> None:
    """Hero carries the 'X committed (recurring + planned)' sub-line."""
    # Set a default so the LDS hero actually surfaces (zero-budget hides it).
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r = client.get("/budget")
    assert r.status_code == 200
    hero = _hero_text(r.text)
    assert "committed" in hero
    assert "(recurring + planned)" in hero


def test_budget_hero_committed_zero_renders_flat_zero(client: TestClient, cat_id: int) -> None:
    """With no recurring + no planned, committed sub-line still renders a zero."""
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r = client.get("/budget")
    assert r.status_code == 200
    assert "0.00 PLN committed" in _hero_text(r.text)


def test_budget_hero_committed_subline_survives_budget_stale_rerender(
    client: TestClient, cat_id: int
) -> None:
    """After mutating a budget (which emits budget-stale) and reloading, the
    sub-line is still present — HTMX-driven re-renders don't drop it."""
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r1 = client.post(f"/budget/defaults/{cat_id}", data={"amount": "200"})
    assert "budget-stale" in r1.headers.get("HX-Trigger", "")
    r2 = client.get("/budget")
    assert r2.status_code == 200
    assert "committed (recurring + planned)" in _hero_text(r2.text)


# ---------------------------------------------------------------------------
# T-133 / ADR-0049 — Monthly summary analytics columns.
# ---------------------------------------------------------------------------
def _seed_three_cats_with_history(settings: Settings) -> None:
    """Seed one account + three expense categories with 2026-09 + 2026-10 txns.

    Food   : prev=300, this=500 → delta=+200 (up)
    Rent   : prev=400, this=400 → delta=   0 (no modifier)
    Fun    : prev=200, this=100 → delta=-100 (down)
    """
    conn = get_connection(settings)
    try:
        acct = accounts_repo.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
        pairs = [
            ("Food", 30000, 50000),
            ("Rent", 40000, 40000),
            ("Fun", 20000, 10000),
        ]
        for name, prev_amt, this_amt in pairs:
            cat_id = categories_repo.create(
                conn, USER_ID, NewCategory(name=name, direction=Direction.EXPENSE)
            ).id
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=date(2026, 9, 15),
                    category_id=cat_id,
                    account_id=acct,
                    amount=prev_amt,
                ),
            )
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=date(2026, 10, 15),
                    category_id=cat_id,
                    account_id=acct,
                    amount=this_amt,
                ),
            )
    finally:
        conn.close()


def test_monthly_summary_renders_analytics_headers(client: TestClient, _migrated: Settings) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    assert r.status_code == 200
    headers = _html.texts(r.text, plan.summary_headers)
    assert "Avg/mo" in headers
    assert "YTD avg" in headers
    # Δ prev — match on prefix so unicode minor variants don't trip the test.
    assert any(h.endswith("prev") for h in headers)


def test_monthly_summary_delta_up_renders_sign_and_class(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    cells = _cells(r.text, "Food")
    # Column order (post-ADR-0049): Category, Planned, Actual, Avg/mo, YTD avg,
    # Δ prev, Remainder-bar, Remainder.
    assert "500.00" in cells[2]
    assert "400.00" in cells[3]  # (500 + 300) / 2 months
    assert "80.00" in cells[4]  # (500 + 300) / 10 elapsed months
    assert "+200.00" in cells[5]  # direction is the sign; colour is checked in e2e


def test_monthly_summary_delta_down_renders_sign_and_class(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    cells = _cells(r.text, "Fun")
    assert "-100.00" in cells[5]  # direction is the sign; colour is checked in e2e


def test_monthly_summary_delta_zero_has_no_sign_modifier(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    delta = _cells(r.text, "Rent")[5]
    assert "0.00" in delta
    assert not delta.startswith(("+", "-"))  # no sign; neutral colour is checked in e2e


def test_monthly_summary_totals_row_leaves_analytics_blank(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    cells = _html.texts(r.text, role("cell").inside(plan.summary_totals_row))
    # Avg/mo, YTD avg, Δ prev all blank in the footer (weighted sums are
    # misleading across differing active-month counts).
    assert cells[3] == ""
    assert cells[4] == ""
    assert cells[5] == ""


# ---------------------------------------------------------------------------
# T-FIX1 / ADR-0085 - unbudgeted commitments are informational only.
# ---------------------------------------------------------------------------
def test_budget_hero_unbudgeted_info_line_not_counted(
    client: TestClient, _migrated: Settings, cat_id: int
) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    # Tomorrow, unless that is next month's day 1 (month-end clock): then today (ADR-0140).
    today = clock.today_local(Settings())
    tomorrow = today + timedelta(days=1)
    planned_day = tomorrow if tomorrow.month == today.month else today
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Chk", currency="PLN")).id
        rent = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        ).id
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=planned_day,
                category_id=rent,
                account_id=acc,
                amount=35_000,
            ),
        )
    finally:
        conn.close()
    r = client.get("/budget")
    hero = _hero_text(r.text)
    assert "+ 350.00 PLN planned in unbudgeted categories (not counted)" in hero
    assert "0.00 PLN committed" in hero


def _texts(html: str, loc: object) -> list[str]:
    return [t.get_text(" ", strip=True) for t in _html.resolve(html, loc)]  # type: ignore[arg-type]


def _hero_text(html: str) -> str:
    return _html.text_of(html, plan.budget_hero)


def _selected_month(html: str) -> list[str]:
    options = _html.resolve(html, plan.option_in(plan.budget_month_select))
    return [str(o.get("value")) for o in options if o.has_attr("selected")]


def _cells(html: str, name: str) -> list[str]:
    return _texts(html, plan.summary_cells(name))


def _month_page(client: TestClient, settings: Settings) -> str:
    _seed_three_cats_with_history(settings)
    html: str = client.get("/budget?year=2026&month=10").text
    return html


def test_budget_breakdown_points_to_plan_analytics(client: TestClient, cat_id: int) -> None:
    """T-R50 (ADR-0054): Breakdown moved to /plan?tab=analytics; /budget keeps a
    pointer section, no chart images."""
    r = client.get("/budget")
    link = _html.resolve_one(r.text, plan.breakdown_link)
    assert link.get("href") == "/plan?tab=analytics"
    assert not _html.exists(r.text, plan.chart_image.inside(plan.budget_breakdown))


def test_inline_override_form_prefills_month_and_year(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?inline=1&month=3&year=2027")
    soup = BeautifulSoup(r.text, "html.parser")
    month = soup.find("input", {"name": "month"})
    year = soup.find("input", {"name": "year"})
    assert isinstance(month, Tag)
    assert isinstance(year, Tag)
    assert (month.get("value"), year.get("value")) == ("3", "2027")


def test_monthly_summary_delta_down_renders_sign(client: TestClient, _migrated: Settings) -> None:
    cells = _cells(_month_page(client, _migrated), "Fun")
    assert "-100.00" in cells[5]
    assert "+" not in cells[5]


def test_monthly_summary_delta_up_renders_sign(client: TestClient, _migrated: Settings) -> None:
    # Column order (post-ADR-0049): Category, Planned, Actual, Avg/mo, YTD avg,
    # Δ prev, Remainder-bar, Remainder.
    cells = _cells(_month_page(client, _migrated), "Food")
    assert "500.00" in cells[2]
    assert "400.00" in cells[3]  # (500 + 300) / 2 months
    assert "80.00" in cells[4]  # (500 + 300) / 10 elapsed months
    assert "+200.00" in cells[5]


def test_monthly_summary_delta_zero_has_no_sign(client: TestClient, _migrated: Settings) -> None:
    cells = _cells(_month_page(client, _migrated), "Rent")
    assert "0.00" in cells[5]
    assert "+" not in cells[5]
    assert "-" not in cells[5]


def test_yearly_fragment_lists_the_category(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget/yearly?year=2026")
    assert _html.exists(r.text, plan.yearly_section)
    assert _html.exists(r.text, plan.yearly_row("Groceries"))
