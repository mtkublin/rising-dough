"""T-039 home + navigation + T-063 overview composition."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import preferences as preferences_service

USER_ID = 1


@pytest.fixture
def seeded(_migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=100000)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        soon = date.today() + timedelta(days=3)  # noqa: DTZ011
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=soon,
                category_id=cat.id,
                account_id=acc.id,
                amount=1000,
                description="Bread",
            ),
        )
    finally:
        conn.close()


def test_home_renders(client: TestClient, seeded: None) -> None:
    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.find(id="fortune") is not None
    assert soup.find(id="budget-card") is not None
    assert soup.find(id="upcoming") is not None


def test_nav_links_present(client: TestClient) -> None:
    """Rising Dough v2 rail — ADR-0051 §1 IA.

    Nav collapses v1 Budget + Forecast + Analytics into /plan (tabs).
    Legacy /transactions, /planned, /recurring still 302 but the rail no
    longer links to them directly.
    """
    r = client.get("/today")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    hrefs = {a["href"] for a in soup.select("nav a")}
    for path in ("/today", "/ledger", "/plan", "/accounts", "/settings"):
        assert path in hrefs, f"nav missing {path}"
    assert "/transactions" not in hrefs
    assert "/budget" not in hrefs
    assert "/forecast" not in hrefs


def test_nav_has_four_primary_items_plus_settings(client: TestClient) -> None:
    r = client.get("/today")
    soup = BeautifulSoup(r.text, "html.parser")
    rail = soup.select_one(".rd-rail")
    assert rail is not None
    primary = rail.select("nav > ul.rd-nav .rd-nav__link")
    footer = rail.select(".rd-rail__footer .rd-nav__link")
    assert len(primary) == 4, f"expected 4 primary rail items, got {len(primary)}"
    # T-D02b: Settings + Security (account block), plus a Sign out form.
    labels = [a.get_text(strip=True) for a in footer]
    assert labels == ["Settingsg s", "Security"], labels
    assert rail.select_one('.rd-rail__account form[action="/auth/logout"]') is not None


def test_shell_slots_present(client: TestClient) -> None:
    """Rising Dough v2 base shell exposes drawer-root + modal-root + toast-root."""
    r = client.get("/today")
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.find(id="drawer-root") is not None
    assert soup.find(id="modal-root") is not None
    assert soup.find(id="toast-root") is not None
    assert soup.select_one(".rd-rail") is not None
    assert soup.select_one(".rd-main") is not None


def test_fortune_shows_base_total(client: TestClient, seeded: None) -> None:
    r = client.get("/")
    assert "1,000.00 PLN" in r.text


def test_upcoming_lists_planned(client: TestClient, seeded: None) -> None:
    r = client.get("/")
    assert "Bread" in r.text


def test_empty_db_home(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "No planned payments in this window." in r.text


def test_overview_three_panels(client: TestClient, _migrated: Settings) -> None:
    """Three panels are present with the asserted IDs + the sum closure line matches."""
    conn = get_connection(_migrated)
    try:
        acc_a = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Alpha", currency="PLN", opening_balance=250000)
        )
        acc_b = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Beta", currency="PLN", opening_balance=150000)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=cat.id, amount=100000))
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date.today(),  # noqa: DTZ011
                category_id=cat.id,
                account_id=acc_a.id,
                amount=200000,  # 2000.00 > 1000.00 budgeted → over_budget
                description="Groceries",
            ),
        )
        assert acc_b.id  # keep ref alive for mypy
    finally:
        conn.close()

    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.select_one('[data-panel="accounts"]') is not None
    assert soup.select_one('[data-panel="month"]') is not None
    assert soup.select_one('[data-panel="upcoming"]') is not None
    assert soup.find(id="fortune") is not None
    assert soup.find(id="budget-card") is not None
    assert soup.find(id="upcoming") is not None

    # Fortune hero + closure line should both render the same total (minus any txn impact).
    # Opening: 2500 + 1500 = 4000.  Expense txn: -2000.  Expected fortune: 2000.00 PLN.
    closure = soup.select_one(".account-list__closure")
    assert closure is not None
    assert "2,000.00 PLN" in closure.get_text()

    # Pace tag should be "over budget" given spent 2000 > budgeted 1000.
    pace = soup.select_one(".pace-tag")
    assert pace is not None
    assert pace.get("data-pace") == "over_budget"
    assert "over budget" in pace.get_text()


def test_overview_upcoming_fragment(client: TestClient, seeded: None) -> None:
    r = client.get("/overview/upcoming?window=7")
    assert r.status_code == 200
    # Fragment: no <html> wrapper, but the list body renders.
    assert "<html" not in r.text.lower()
    assert "Bread" in r.text


def test_overview_upcoming_recurring_row_actions(client: TestClient, _migrated: Settings) -> None:
    """T-121: a recurring rule whose ``next_due`` falls in the 30-day window
    renders a `[data-kind="recurring"]` row with Promote / Skip / Override
    action buttons wired to the ADR-0038 endpoints."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=12_000,
                default_description="Recurring rent",
            ),
        )
        next_due = date.today() + timedelta(days=5)  # noqa: DTZ011
        recurring_repo.update_rule(
            conn,
            USER_ID,
            rule.id,
            PatchRecurringRule(next_due=next_due),
        )
    finally:
        conn.close()

    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    rec_row = soup.select_one('.upcoming-row[data-kind="recurring"]')
    assert rec_row is not None and isinstance(rec_row, Tag)
    # Row should NOT render the overdue chip even if next_due is close.
    assert "upcoming-row--overdue" not in (rec_row.get("class") or [])
    actions = rec_row.select(".upcoming-row__action")
    hx_targets: set[str] = {str(btn.get("hx-get") or btn.get("hx-post") or "") for btn in actions}
    assert f"/recurring/{rule.id}/promote" in hx_targets
    assert f"/recurring/{rule.id}/skip-next" in hx_targets
    assert any(
        val.startswith(f"/recurring/{rule.id}/overrides/new?occurrence_date=") for val in hx_targets
    )
    skip_btn = rec_row.select_one('[hx-post$="/skip-next"]')
    assert skip_btn is not None and isinstance(skip_btn, Tag)
    assert skip_btn.get("hx-confirm") == "Skip the next occurrence?"


def test_overview_overdue_planned_row_persists_italic(
    client: TestClient, _migrated: Settings
) -> None:
    """T-121: a persisted planned row whose operation_date is in the past
    still renders inside the upcoming list with the overdue chip + italic
    styling (recurring rows never render overdue; planned rows always do)."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        past = date.today() - timedelta(days=4)  # noqa: DTZ011
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=past,
                category_id=cat.id,
                account_id=acc.id,
                amount=4200,
                description="Late bill",
            ),
        )
    finally:
        conn.close()

    r = client.get("/")
    soup = BeautifulSoup(r.text, "html.parser")
    row = soup.select_one('.upcoming-row[data-kind="planned"]')
    assert row is not None and isinstance(row, Tag)
    classes: list[str] = list(row.get("class") or [])
    assert "upcoming-row--overdue" in classes
    assert "overdue" in row.get_text().lower()


def test_overview_upcoming_add_recurring_wired(client: TestClient) -> None:
    """T-121: `+ Recurring` button opens the slide-over at `/recurring/new`."""
    r = client.get("/")
    soup = BeautifulSoup(r.text, "html.parser")
    btn = soup.select_one('.panel--upcoming button[aria-label="Add recurring rule"]')
    assert btn is not None and isinstance(btn, Tag)
    assert btn.get("hx-get") == "/recurring/new"
    assert btn.get("hx-target") == "#modal-root"


def test_overview_upcoming_add_buttons_grouped(client: TestClient) -> None:
    """T-121: `+ Planned` + `+ Recurring` live inside `.panel__add-group`."""
    r = client.get("/")
    soup = BeautifulSoup(r.text, "html.parser")
    group = soup.select_one(".panel--upcoming .panel__add-group")
    assert group is not None and isinstance(group, Tag)
    labels = {btn.get("aria-label") for btn in group.select("button")}
    assert "Add planned payment" in labels
    assert "Add recurring rule" in labels


def test_overview_upcoming_fragment_oob_segmented(client: TestClient, seeded: None) -> None:
    """T-093 — fragment returns an out-of-band swap of the segmented range so
    active state follows the chosen window without any JS."""
    r = client.get("/overview/upcoming?window=30")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    seg = soup.find(id="upcoming-range")
    assert seg is not None and isinstance(seg, Tag)
    assert seg.get("hx-swap-oob") == "outerHTML"
    active = seg.select_one('button[data-view="30"], button[aria-pressed="true"]')
    assert active is not None and isinstance(active, Tag)
    assert active.get("aria-pressed") == "true"
    assert "30 days" in active.get_text()


def test_overview_upcoming_plus_planned_wired(client: TestClient, seeded: None) -> None:
    """T-093 — ``+ Planned`` button is a working HTMX trigger, not a
    placeholder."""
    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    add_btn = soup.select_one(".panel--upcoming .panel__add")
    assert add_btn is not None and isinstance(add_btn, Tag)
    assert add_btn.get("hx-get") == "/planned/new"
    assert add_btn.get("hx-target") == "#modal-root"
    assert add_btn.get("data-add-kind") is None


def test_overview_overdue_muted(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        past = date.today() - timedelta(days=3)  # noqa: DTZ011
        future = date.today() + timedelta(days=3)  # noqa: DTZ011
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=past,
                category_id=cat.id,
                account_id=acc.id,
                amount=5000,
                description="Overdue bill",
            ),
        )
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=future,
                category_id=cat.id,
                account_id=acc.id,
                amount=6000,
                description="Future bill",
            ),
        )
    finally:
        conn.close()

    r = client.get("/")
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".upcoming-row")
    assert len(rows) == 2
    overdue = [r for r in rows if "Overdue bill" in r.get_text()]
    future_rows = [r for r in rows if "Future bill" in r.get_text()]
    assert overdue and "upcoming-row--overdue" in (overdue[0].get("class") or [])
    assert future_rows and "upcoming-row--overdue" not in (future_rows[0].get("class") or [])
    assert "overdue" in overdue[0].get_text().lower()


def test_overview_upcoming_union_planned_plus_recurring(
    client: TestClient, _migrated: Settings
) -> None:
    """T-119: Upcoming fragment surfaces both planned + recurring rows and
    recurring rows carry ``data-kind="recurring"``."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        soon = date.today() + timedelta(days=3)  # noqa: DTZ011
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=soon,
                category_id=cat.id,
                account_id=acc.id,
                amount=4200,
                description="Future planned",
            ),
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=12_000,
                default_description="Recurring rent",
            ),
        )
        # Pin next_due into the 30-day window (ADR-0038 admin override).
        recurring_repo.update_rule(
            conn,
            USER_ID,
            rule.id,
            PatchRecurringRule(next_due=date.today() + timedelta(days=5)),  # noqa: DTZ011
        )
    finally:
        conn.close()

    r = client.get("/overview/upcoming?window=30")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".upcoming-row")
    assert len(rows) == 2
    descriptions = [row.get_text() for row in rows]
    assert any("Future planned" in d for d in descriptions)
    assert any("Recurring rent" in d for d in descriptions)
    recurring_rows = soup.select('.upcoming-row[data-kind="recurring"]')
    planned_rows = soup.select('.upcoming-row[data-kind="planned"]')
    assert len(recurring_rows) == 1
    assert len(planned_rows) == 1


def test_overview_promoted_hidden(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        soon = date.today() + timedelta(days=2)  # noqa: DTZ011
        planned_row = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=soon,
                category_id=cat.id,
                account_id=acc.id,
                amount=4200,
                description="Already promoted",
            ),
        )
        # Create a transaction to attach then stamp promotion.
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=soon,
                category_id=cat.id,
                account_id=acc.id,
                amount=4200,
                description="Already promoted",
                promoted_from_planned_id=planned_row.id,
            ),
        )
        planned_repo.stamp_promotion(conn, USER_ID, planned_row.id, txn.id)
    finally:
        conn.close()

    r = client.get("/overview/upcoming?window=30")
    assert r.status_code == 200
    assert "Already promoted" not in r.text
    assert "No planned payments in this window." in r.text


# ---------------------------------------------------------------------------
# T-084 — home dashboard shows Assets / Liabilities / Net worth (ADR-0024)


def test_home_renders_assets_liabilities_net(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        accounts_repo.create(
            conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=100_000)
        )
        accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa",
                currency="PLN",
                is_liability=True,
                credit_limit_minor=1_000_000,
            ),
        )
    finally:
        conn.close()
    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    panel = soup.find(id="fortune")
    assert panel is not None
    text = panel.get_text()
    assert "Assets" in text
    assert "Liabilities" in text
    assert "Net worth" in text


# ---------------------------------------------------------------------------
# T-120 / ADR-0039 — committed sub-line on the Overview Month panel.
# ---------------------------------------------------------------------------


def test_month_panel_renders_committed_subline(client: TestClient, _migrated: Settings) -> None:
    """Overview Month panel carries the 'X committed (recurring + planned)' sub-line."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        budgets_repo.set_default(
            conn, USER_ID, NewBudgetDefault(category_id=cat.id, amount=100_000)
        )
        assert acc.id  # keep ref alive
    finally:
        conn.close()
    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    panel = soup.find(id="budget-card")
    assert isinstance(panel, Tag)
    committed = panel.select_one(".panel__hero-sub--committed")
    assert isinstance(committed, Tag)
    assert "committed" in committed.get_text(" ", strip=True)
    # Zero-committed renders as data-committed="0".
    assert committed.get("data-committed") == "0"


# ---------------------------------------------------------------------------
# ADR-0041 — Overview Month panel days-left mirrors Budget period cutoff.
# ---------------------------------------------------------------------------


def test_month_panel_days_left_uses_period_cutoff(client: TestClient, _migrated: Settings) -> None:
    """Overview 'This month' banner reports days until next income anchor,
    not the end-of-month residual (ADR-0041 F4.6 alignment)."""
    today = datetime.now(ZoneInfo(_migrated.display_timezone)).date()
    next_income = today + timedelta(days=5)
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=100000)
        )
        salary = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        groceries = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        budgets_repo.set_default(
            conn, USER_ID, NewBudgetDefault(category_id=groceries.id, amount=100_000)
        )
        preferences_service.set_income_anchor_category_id(conn, 1, salary.id)
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=next_income,
                category_id=salary.id,
                account_id=acc.id,
                amount=500_000,
                description="Salary",
            ),
        )
    finally:
        conn.close()

    r = client.get("/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    panel = soup.find(id="budget-card")
    assert isinstance(panel, Tag)
    caption = panel.get_text(" ", strip=True)
    assert "5 days left" in caption, caption
