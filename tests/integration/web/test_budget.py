"""T-036 budget router."""

from __future__ import annotations

from datetime import date

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)

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


def test_index(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    assert "Budget" in r.text


def test_index_with_year_month(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=10")
    assert r.status_code == 200
    assert "2026-10" in r.text


def test_manage_page_redirects_to_budget_rules(client: TestClient, cat_id: int) -> None:
    """T-070: ``/budget/manage`` returns 302 to ``/budget#budget-rules``."""
    r = client.get("/budget/manage", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/budget#budget-rules"


def test_set_default(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "500"})
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_set_default_404(client: TestClient) -> None:
    r = client.post("/budget/defaults/9999", data={"amount": "100"})
    assert r.status_code == 404


def test_set_default_invalid(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "nan"})
    assert r.status_code == 422


def test_set_default_negative(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "-5"})
    assert r.status_code == 422


def test_set_recurring(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/recurring/{cat_id}/5", data={"amount": "200"})
    assert r.status_code == 200


def test_set_recurring_404(client: TestClient) -> None:
    r = client.post("/budget/recurring/9999/5", data={"amount": "1"})
    assert r.status_code == 404


def test_set_recurring_bad_month(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/recurring/{cat_id}/13", data={"amount": "1"})
    assert r.status_code == 422


def test_set_recurring_bad_amount(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/recurring/{cat_id}/5", data={"amount": "nope"})
    assert r.status_code == 422


def test_set_one_off(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/one-off/{cat_id}/2026/10", data={"amount": "99"})
    assert r.status_code == 200


def test_set_one_off_404(client: TestClient) -> None:
    r = client.post("/budget/one-off/9999/2026/10", data={"amount": "1"})
    assert r.status_code == 404


def test_set_one_off_bad_month(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/one-off/{cat_id}/2026/14", data={"amount": "1"})
    assert r.status_code == 422


def test_set_one_off_bad_amount(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/budget/one-off/{cat_id}/2026/10", data={"amount": "nope"})
    assert r.status_code == 422


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
    assert "2026-10" in r_oct.text
    assert "2026-11" in r_nov.text
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
    assert not breakdown.select("[data-plotly]")
    assert breakdown.find("a", href="/plan?tab=analytics") is not None


def test_budget_manage_lands_on_rules_section(client: TestClient, cat_id: int) -> None:
    """``/budget/manage`` follows to ``/budget`` and the Rules section is present."""
    r = client.get("/budget/manage")  # follow_redirects=True by default
    assert r.status_code == 200
    assert "Rules" in r.text


# ---------------------------------------------------------------------------
# T-113 / ADR-0031 — Rules Override dispatcher + Yearly budget grid
# ---------------------------------------------------------------------------


def test_yearly_fragment_renders_for_year(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget/yearly?year=2026")
    assert r.status_code == 200
    assert 'id="budget-yearly"' in r.text
    assert "Groceries" in r.text


def test_rules_section_renders_override_button(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    assert f"/budget/rules/{cat_id}/overrides/new" in r.text


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


def test_plan_budget_override_button_targets_per_row_slot(client: TestClient, cat_id: int) -> None:
    """T-D49: each Override button targets its own slot row; ids are unique."""
    r = client.get("/plan?tab=budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    btn = soup.find("button", {"data-override-open": str(cat_id)})
    assert isinstance(btn, Tag)
    assert btn.get("hx-target") == f"#override-slot-{cat_id}"
    slot = soup.find("td", {"id": f"override-slot-{cat_id}"})
    assert isinstance(slot, Tag)
    assert slot.get("colspan") == "6"
    row = slot.find_parent("tr")
    assert isinstance(row, Tag)
    btn_row = btn.find_parent("tr")
    assert isinstance(btn_row, Tag)
    assert btn_row.find_next_sibling("tr") is row
    ids = [t["id"] for t in soup.find_all(id=True)]
    assert len(ids) == len(set(ids))
    assert soup.find(id="budget-override-slot") is None


def test_inline_override_form_is_fragment_with_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?inline=1")
    assert r.status_code == 200
    assert "<html" not in r.text
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.select_one("form[data-override-form]")
    assert isinstance(form, Tag)
    assert form.has_attr("data-override-inline")
    assert soup.select_one("[data-override-cancel]") is not None
    assert "<script" not in r.text.split("</form>")[0]


def test_slideover_override_form_has_no_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new")
    assert "data-override-cancel" not in r.text


def test_new_override_form_404_for_unknown_category(client: TestClient) -> None:
    r = client.get("/budget/rules/9999/overrides/new")
    assert r.status_code == 404


def test_new_override_form_returns_slide_over(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new")
    assert r.status_code == 200
    assert 'name="tier"' in r.text
    assert 'name="month"' in r.text
    assert 'name="amount"' in r.text


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


def test_create_override_404_for_unknown_category(client: TestClient) -> None:
    r = client.post(
        "/budget/rules/9999/overrides",
        data={"tier": "recurring", "month": "6", "amount": "1"},
    )
    assert r.status_code == 404


def test_create_override_rejects_bad_tier(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "monthly", "month": "6", "amount": "1"},
    )
    assert r.status_code == 422


def test_create_override_rejects_bad_month(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "recurring", "month": "13", "amount": "1"},
    )
    assert r.status_code == 422


def test_create_override_rejects_bad_amount(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "recurring", "month": "6", "amount": "nope"},
    )
    assert r.status_code == 422


def test_create_override_one_off_rejects_bad_year(client: TestClient, cat_id: int) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "one-off", "month": "7", "year": "bogus", "amount": "1"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# T-120 / ADR-0039 — committed sub-line beneath left-daily-spend hero.
# ---------------------------------------------------------------------------
def test_budget_hero_renders_committed_subline(client: TestClient, cat_id: int) -> None:
    """Hero carries the 'X committed (recurring + planned)' sub-line."""
    # Set a default so the LDS hero actually surfaces (zero-budget hides it).
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r = client.get("/budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    hero = soup.find(id="left-daily-spend")
    assert isinstance(hero, Tag)
    committed = hero.select_one(".budget-lds__committed")
    assert isinstance(committed, Tag)
    assert "committed" in committed.get_text(" ", strip=True)
    assert "recurring + planned" in committed.get_text(" ", strip=True)


def test_budget_hero_committed_zero_renders_flat_zero(client: TestClient, cat_id: int) -> None:
    """With no recurring + no planned, committed sub-line still renders a zero."""
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r = client.get("/budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    hero = soup.find(id="left-daily-spend")
    assert isinstance(hero, Tag)
    committed = hero.select_one(".budget-lds__committed")
    assert isinstance(committed, Tag)
    assert committed.get("data-committed") == "0"


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
    soup = BeautifulSoup(r2.text, "html.parser")
    assert soup.select_one(".budget-lds__committed") is not None


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


def _summary_row(soup: BeautifulSoup, category_name: str) -> Tag:
    table = soup.select_one("table.budget-row-table")
    assert isinstance(table, Tag)
    for row in table.select("tbody tr"):
        if category_name in row.get_text():
            return row
    raise AssertionError(f"row for {category_name} not found")


def _classes(tag: Tag) -> list[str]:
    raw = tag.get("class")
    if raw is None:
        return []
    if isinstance(raw, str):
        return raw.split()
    return list(raw)


def test_monthly_summary_renders_analytics_headers(client: TestClient, _migrated: Settings) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.select_one("table.budget-row-table")
    assert isinstance(table, Tag)
    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    assert "Avg/mo" in headers
    assert "YTD avg" in headers
    # Δ prev — match on prefix so unicode minor variants don't trip the test.
    assert any(h.endswith("prev") for h in headers)


def test_monthly_summary_delta_up_renders_sign_and_class(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    soup = BeautifulSoup(r.text, "html.parser")
    row = _summary_row(soup, "Food")
    cells = row.select("td")
    # Column order (post-ADR-0049): Category, Planned, Actual, Avg/mo, YTD avg,
    # Δ prev, Remainder-bar, Remainder.
    assert "500.00" in cells[2].get_text()
    assert "400.00" in cells[3].get_text()  # (500 + 300) / 2 months
    assert "80.00" in cells[4].get_text()  # (500 + 300) / 10 elapsed months
    delta = cells[5]
    assert "+200.00" in delta.get_text()
    assert "delta--up" in _classes(delta)


def test_monthly_summary_delta_down_renders_sign_and_class(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    soup = BeautifulSoup(r.text, "html.parser")
    row = _summary_row(soup, "Fun")
    cells = row.select("td")
    delta = cells[5]
    assert "-100.00" in delta.get_text()
    assert "delta--down" in _classes(delta)
    assert "delta--up" not in _classes(delta)


def test_monthly_summary_delta_zero_has_no_sign_modifier(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    soup = BeautifulSoup(r.text, "html.parser")
    row = _summary_row(soup, "Rent")
    cells = row.select("td")
    delta = cells[5]
    assert "0.00" in delta.get_text()
    classes = _classes(delta)
    assert "delta--up" not in classes
    assert "delta--down" not in classes


def test_monthly_summary_responsive_hide_class_on_ytd_and_delta(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    soup = BeautifulSoup(r.text, "html.parser")
    row = _summary_row(soup, "Food")
    cells = row.select("td")
    assert "col-hide-sm" not in _classes(cells[3])  # Avg/mo stays visible
    assert "col-hide-sm" in _classes(cells[4])  # YTD avg hidden
    assert "col-hide-sm" in _classes(cells[5])  # Δ prev hidden


def test_monthly_summary_totals_row_leaves_analytics_blank(
    client: TestClient, _migrated: Settings
) -> None:
    _seed_three_cats_with_history(_migrated)
    r = client.get("/budget?year=2026&month=10")
    soup = BeautifulSoup(r.text, "html.parser")
    totals = soup.select_one("tr.budget-row--totals")
    assert isinstance(totals, Tag)
    cells = totals.select("td")
    # Avg/mo, YTD avg, Δ prev all blank in the footer (weighted sums are
    # misleading across differing active-month counts).
    assert cells[3].get_text(strip=True) == ""
    assert cells[4].get_text(strip=True) == ""
    assert cells[5].get_text(strip=True) == ""
