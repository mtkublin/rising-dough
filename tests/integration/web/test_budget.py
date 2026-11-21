"""T-036 budget router: page content through the UI map (T-UT04d, ADR-0106).

Status / redirect / HX-* / audit behaviour of the budget routes lives in
``tests/contract/test_plan_budget.py`` and ``test_plan_views.py``.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, plan
from tests.ui_map.locator import by_id

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


def _texts(html: str, loc: object) -> list[str]:
    return [t.get_text(" ", strip=True) for t in _html.resolve(html, loc)]  # type: ignore[arg-type]


def _hero_text(html: str) -> str:
    return _html.text_of(html, plan.budget_hero)


def _selected_month(html: str) -> list[str]:
    options = _html.resolve(html, plan.option_in(plan.budget_month_select))
    return [str(o.get("value")) for o in options if o.has_attr("selected")]


def test_index(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.heading)
    assert _html.exists(r.text, plan.budget_summary)


def test_index_with_year_month(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=10")
    assert _html.resolve_one(r.text, plan.budget_year_input).get("value") == "2026"
    assert _selected_month(r.text) == ["10"]


def test_budget_month_selector_swaps(client: TestClient, cat_id: int) -> None:
    """Changing ``?month=`` moves the selected month in the picker."""
    r_oct = client.get("/budget?year=2026&month=10")
    r_nov = client.get("/budget?year=2026&month=11")
    assert _selected_month(r_oct.text) == ["10"]
    assert _selected_month(r_nov.text) == ["11"]


def test_budget_breakdown_points_to_plan_analytics(client: TestClient, cat_id: int) -> None:
    """T-R50 (ADR-0054): Breakdown moved to /plan?tab=analytics; /budget keeps a
    pointer section, no chart images."""
    r = client.get("/budget")
    link = _html.resolve_one(r.text, plan.breakdown_link)
    assert link.get("href") == "/plan?tab=analytics"
    assert not _html.exists(r.text, plan.chart_image.inside(plan.budget_breakdown))


def test_budget_manage_lands_on_rules_section(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget/manage")  # follows the redirect
    assert r.status_code == 200
    assert _html.exists(r.text, plan.budget_rules)


def test_yearly_fragment_lists_the_category(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget/yearly?year=2026")
    assert _html.exists(r.text, plan.yearly_section)
    assert _html.exists(r.text, plan.yearly_row("Groceries"))


def test_rules_section_renders_override_button(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget")
    button = _html.resolve_one(r.text, plan.rules_override_button("Groceries"))
    assert button.get("hx-get") == f"/budget/rules/{cat_id}/overrides/new"


def test_rules_default_input_renders_major_decimal(client: TestClient, cat_id: int) -> None:
    """1550 minor renders as "15.50", not the raw int."""
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "15.50"})
    r = client.get("/budget")
    assert _html.resolve_one(r.text, plan.rule_default_input(cat_id)).get("value") == "15.50"


def test_yearly_cell_renders_major_decimal(client: TestClient, cat_id: int) -> None:
    client.post(f"/budget/one-off/{cat_id}/2026/7", data={"amount": "22.33"})
    r = client.get("/budget/yearly?year=2026")
    assert _html.resolve_one(r.text, plan.yearly_input(cat_id, 7)).get("value") == "22.33"


def test_plan_budget_override_button_targets_per_row_slot(client: TestClient, cat_id: int) -> None:
    """T-D49: each Override button targets its own slot row; ids are unique."""
    r = client.get("/plan?tab=budget")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    btn = _html.resolve_one(soup, plan.override_button("Groceries"))
    assert btn.get("hx-target") == f"#override-slot-{cat_id}"
    slot = _html.resolve_one(soup, plan.override_slot(cat_id))
    assert slot.get("colspan") == "6"
    row = slot.find_parent("tr")
    assert isinstance(row, Tag)
    btn_row = btn.find_parent("tr")
    assert isinstance(btn_row, Tag)
    assert btn_row.find_next_sibling("tr") is row
    # T-D49a: closed slot is empty and its row is hidden by CSS (no row gaps).
    assert slot.get_text(strip=True) == "" and not slot.find(True)
    assert _html.exists(soup, plan.override_row(cat_id))
    static = Path(__file__).resolve().parents[3] / "src/budget_planner/web/static"
    css = (static / "rising-dough.css").read_text()
    assert ".rd-override-slot-row:not(:has(.rd-override)) { display: none; }" in css
    ids = [t["id"] for t in soup.find_all(id=True)]
    assert len(ids) == len(set(ids))
    assert not _html.exists(soup, by_id("budget-override-slot"))


def test_inline_override_form_prefills_month_and_year(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?inline=1&month=3&year=2027")
    soup = BeautifulSoup(r.text, "html.parser")
    month = soup.find("input", {"name": "month"})
    year = soup.find("input", {"name": "year"})
    assert isinstance(month, Tag)
    assert isinstance(year, Tag)
    assert (month.get("value"), year.get("value")) == ("3", "2027")


# ---------------------------------------------------------------------------
# T-120 / ADR-0039 — committed sub-line beneath left-daily-spend hero.
# ---------------------------------------------------------------------------
_ZERO_COMMITTED = re.compile(r"\b0[.,]00\b[^()]*committed")


def test_budget_hero_renders_committed_subline(client: TestClient, cat_id: int) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    text = _hero_text(client.get("/budget").text)
    assert "committed" in text
    assert "recurring + planned" in text


def test_budget_hero_committed_zero_renders_flat_zero(client: TestClient, cat_id: int) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    assert _ZERO_COMMITTED.search(_hero_text(client.get("/budget").text))


def test_budget_hero_committed_subline_survives_budget_stale_rerender(
    client: TestClient, cat_id: int
) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    r1 = client.post(f"/budget/defaults/{cat_id}", data={"amount": "200"})
    assert "budget-stale" in r1.headers.get("HX-Trigger", "")
    assert "recurring + planned" in _hero_text(client.get("/budget").text)


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


def _cells(html: str, name: str) -> list[str]:
    return _texts(html, plan.summary_cells(name))


def _month_page(client: TestClient, settings: Settings) -> str:
    _seed_three_cats_with_history(settings)
    html: str = client.get("/budget?year=2026&month=10").text
    return html


def test_monthly_summary_renders_analytics_headers(client: TestClient, _migrated: Settings) -> None:
    headers = _texts(_month_page(client, _migrated), plan.summary_headers)
    assert "Avg/mo" in headers
    assert "YTD avg" in headers
    # Δ prev — match on suffix so unicode minor variants don't trip the test.
    assert any(h.endswith("prev") for h in headers)


def test_monthly_summary_delta_up_renders_sign(client: TestClient, _migrated: Settings) -> None:
    # Column order (post-ADR-0049): Category, Planned, Actual, Avg/mo, YTD avg,
    # Δ prev, Remainder-bar, Remainder.
    cells = _cells(_month_page(client, _migrated), "Food")
    assert "500.00" in cells[2]
    assert "400.00" in cells[3]  # (500 + 300) / 2 months
    assert "80.00" in cells[4]  # (500 + 300) / 10 elapsed months
    assert "+200.00" in cells[5]


def test_monthly_summary_delta_down_renders_sign(client: TestClient, _migrated: Settings) -> None:
    cells = _cells(_month_page(client, _migrated), "Fun")
    assert "-100.00" in cells[5]
    assert "+" not in cells[5]


def test_monthly_summary_delta_zero_has_no_sign(client: TestClient, _migrated: Settings) -> None:
    cells = _cells(_month_page(client, _migrated), "Rent")
    assert "0.00" in cells[5]
    assert "+" not in cells[5]
    assert "-" not in cells[5]


def test_monthly_summary_totals_row_leaves_analytics_blank(
    client: TestClient, _migrated: Settings
) -> None:
    html = _month_page(client, _migrated)
    totals = _texts(html, plan.role_in("cell", plan.summary_totals_row))
    # Avg/mo, YTD avg, Δ prev blank in the footer (weighted sums mislead).
    assert totals[3] == totals[4] == totals[5] == ""


# ---------------------------------------------------------------------------
# T-FIX1 / ADR-0085 - unbudgeted commitments are informational only.
# ---------------------------------------------------------------------------
def test_budget_hero_unbudgeted_info_line_not_counted(
    client: TestClient, _migrated: Settings, cat_id: int
) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
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
                operation_date=datetime.now(UTC).date() + timedelta(days=1),
                category_id=rent,
                account_id=acc,
                amount=35_000,
            ),
        )
    finally:
        conn.close()
    text = _hero_text(client.get("/budget").text)
    assert re.search(r"350[.,]00\b.*planned in unbudgeted categories \(not counted\)", text)
    assert _ZERO_COMMITTED.search(text)  # unbudgeted plans are not counted as committed
