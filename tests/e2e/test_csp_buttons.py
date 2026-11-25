"""E2E under the prod CSP: the buttons that broke in prod v3.0.1 (T-D140c, ADR-0113).

The ``page`` fixture serves every HTML response with the CSP parsed from
``Caddyfile.tpl`` and fails the test on any CSP violation, so these tests
only need to drive the UI and assert its visible result.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import fx as fx_repo
from tests.e2e import db_probe
from tests.e2e.ui_actions import open_add_slide_over, pick
from tests.ui_map import accounts, ledger, plan_budget, plan_year, settings, shell, today
from tests.ui_map.locator import Locator as UiLocator, role, to_playwright

pytestmark = pytest.mark.e2e

_SLIDE = shell.slideover
_ADDED_MINOR = 1234
SKIP_REASON = "T-UR07b: new-entry/promote dialogs not ported yet"
# Old Today toolbar and promote-dialog buttons; T-UR07b re-enables these tests on the new dialogs.
ADD_PLANNED = role("button", "+ Planned")
ADD_RECURRING = role("button", "+ Recurring")
CONFIRM_PROMOTE = role("button", "Confirm")


def _seed(base_url: str, db_path: Path, page: Page, category: str = "Groceries") -> tuple[str, str]:
    """Create one account + one expense category; return (account_id, category_id)."""
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": category, "direction": "expense"},
    ).ok
    return str(db_probe.account_id(db_path, "Checking")), str(
        db_probe.category_id(db_path, category)
    )


def _fill(page: Page, field: UiLocator, value: str, scope: UiLocator = _SLIDE) -> None:
    to_playwright(page, field.inside(scope)).fill(value)


def _submit(page: Page, button: UiLocator, scope: UiLocator = _SLIDE) -> None:
    to_playwright(page, button.inside(scope)).click()


def _open_add_slide_over(page: Page, base_url: str, route: str) -> None:
    page.goto(f"{base_url}{route}")
    open_add_slide_over(page)
    expect(to_playwright(page, ledger.form)).to_be_visible()


@pytest.mark.skip(
    reason="T-UR07b ports the new-entry and promote dialogs; the old slide-over is gone from Today"
)
def test_add_slide_over_on_today_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_add_slide_over(page, base_url, "/today")
    # Combobox + close behaviour are static JS and must work under the CSP.
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    expect(to_playwright(page, ledger.field_category.inside(_SLIDE))).to_have_value("Groceries")
    _submit(page, ledger.cancel_button)
    expect(to_playwright(page, ledger.form)).to_have_count(0)


@pytest.mark.skip(
    reason="T-UR07b ports the new-entry and promote dialogs; the old slide-over is gone from Today"
)
def test_add_from_today_submits_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_add_slide_over(page, base_url, "/today")
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    _fill(page, ledger.field_amount, "12.34")
    _fill(page, ledger.field_note, "today-added")
    _submit(page, ledger.add_entry)
    # Overlay closes and Today reloads: the 500.00 opening balance drops by 12.34.
    expect(to_playwright(page, ledger.form)).to_have_count(0)
    expect(to_playwright(page, shell.main)).to_contain_text("487.66")
    assert db_probe.txn_amounts(db_path, "today-added") == [_ADDED_MINOR]
    page.goto(f"{base_url}/ledger?view=actual")
    expect(to_playwright(page, ledger.table_container)).to_contain_text("today-added")


@pytest.mark.skip(
    reason="T-UR07b ports the new-entry and promote dialogs; the old slide-over is gone from Today"
)
def test_add_from_today_invalid_amount_rerenders_form(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_add_slide_over(page, base_url, "/today")
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    _fill(page, ledger.field_amount, "0")
    _submit(page, ledger.add_entry)
    expect(to_playwright(page, ledger.form)).to_have_count(1)
    expect(to_playwright(page, ledger.form)).to_contain_text("amount")
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM transactions") == 0


def test_add_slide_over_on_ledger_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_add_slide_over(page, base_url, "/ledger")
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    _fill(page, ledger.field_amount, "12.34")
    _fill(page, ledger.field_note, "csp-added")
    _submit(page, ledger.add_entry)
    expect(to_playwright(page, ledger.view_table("actual"))).to_contain_text("csp-added")
    assert db_probe.txn_amounts(db_path, "csp-added") == [_ADDED_MINOR]


@pytest.mark.skip(reason=SKIP_REASON)
def test_promote_on_today_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    account_id, category_id = _seed(base_url, db_path, page)
    soon = datetime.now(tz=UTC).date() + timedelta(days=2)
    assert page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": soon.isoformat(),
            "category_id": category_id,
            "account_id": account_id,
            "amount": "25.00",
            "description": "csp-promote",
        },
    ).ok
    planned_row = today.upcoming_planned(db_probe.planned_id(db_path, "csp-promote"))

    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, today.promote.inside(planned_row)).first.click()
    to_playwright(page, CONFIRM_PROMOTE).click()
    # The promoted planned item leaves Upcoming and lands in the ledger.
    expect(to_playwright(page, planned_row)).to_have_count(0)
    assert db_probe.txn_amounts(db_path, "csp-promote") == [2500]
    page.goto(f"{base_url}/ledger?view=actual")
    expect(to_playwright(page, ledger.table_container)).to_contain_text("csp-promote")


def test_override_on_plan_budget_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _, category_id = _seed(base_url, db_path, page)
    assert page.request.post(
        f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}
    ).ok

    page.goto(f"{base_url}/plan?tab=budget&year=2026&month=10")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, plan_budget.row_menu_button("Groceries")).click()
    to_playwright(page, plan_budget.override_item("Groceries")).click()
    dialog = plan_year.dialog("Groceries", "Oct 2026")
    expect(to_playwright(page, dialog)).to_be_visible()
    # The scope radio is visually hidden (its label is the click target).
    to_playwright(page, plan_year.tier(dialog, "new default")).dispatch_event("click")
    to_playwright(page, plan_year.amount(dialog)).fill("321.00")
    to_playwright(page, plan_year.save(dialog)).click()
    # The dialog closes and the budget table re-renders with the override applied.
    expect(to_playwright(page, dialog)).to_have_count(0)
    expect(to_playwright(page, plan_budget.row("Groceries"))).to_contain_text("321.00")
    assert (
        db_probe.scalar(
            db_path,
            "SELECT amount FROM budget_defaults WHERE category_id = ? AND deleted_at IS NULL",
            int(category_id),
        )
        == 32100
    )


def _open_today_form(page: Page, base_url: str, button: UiLocator, form: UiLocator) -> None:
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, button).click()
    expect(to_playwright(page, form)).to_be_visible()


@pytest.mark.skip(reason=SKIP_REASON)
def test_add_planned_from_today_submits_under_csp(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_today_form(page, base_url, ADD_PLANNED, ledger.planned_form)
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    soon = datetime.now(tz=UTC).date() + timedelta(days=2)
    _fill(page, ledger.field_date, soon.isoformat())
    _fill(page, ledger.field_amount, "25.00")
    _fill(page, ledger.field_note, "today-planned")
    _submit(page, ledger.add_entry)
    expect(to_playwright(page, ledger.planned_form)).to_have_count(0)
    planned_row = today.upcoming_planned(db_probe.planned_id(db_path, "today-planned"))
    expect(to_playwright(page, planned_row)).to_be_visible()
    page.goto(f"{base_url}/ledger?view=planned")
    expect(to_playwright(page, ledger.table_container)).to_contain_text("today-planned")


@pytest.mark.skip(reason=SKIP_REASON)
def test_add_planned_from_today_invalid_amount_rerenders_form(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_today_form(page, base_url, ADD_PLANNED, ledger.planned_form)
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    _fill(page, ledger.field_amount, "0")
    _submit(page, ledger.add_entry)
    expect(to_playwright(page, ledger.planned_form)).to_have_count(1)
    expect(to_playwright(page, ledger.planned_form)).to_contain_text("amount")
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM planned_transactions") == 0


@pytest.mark.skip(reason=SKIP_REASON)
def test_add_recurring_from_today_submits_under_csp(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    _open_today_form(page, base_url, ADD_RECURRING, ledger.recurring_form)
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    _fill(page, ledger.field_default_amount, "40.00")
    _fill(page, ledger.field_note, "today-rule")
    _submit(page, ledger.add_rule_button)
    expect(to_playwright(page, ledger.recurring_form)).to_have_count(0)
    rule = ledger.recurring_row(db_probe.rule_id(db_path, "today-rule"))
    page.goto(f"{base_url}/ledger?view=recurring")
    expect(to_playwright(page, rule)).to_be_visible()


def _open_new_account_form(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/accounts")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, accounts.new_account_button).click()
    expect(to_playwright(page, accounts.account_form)).to_be_visible()


@pytest.mark.skip(
    reason="T-UR08b: the new-account form currency combobox is not wired in the new shell"
)
def test_create_account_from_accounts_submits_under_csp(
    live_server: tuple[str, Path], page: Page
) -> None:
    # T-D150: the create form targeted a non-existent #accounts-grid.
    base_url, db_path = live_server
    # Net worth converts every account to base (ADR-0139): a EUR account needs a cached rate.
    conn = get_connection(Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}"))
    try:
        fx_repo.upsert_rate(
            conn,
            NewFxRate(date=date(2020, 1, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
        )
    finally:
        conn.close()
    _open_new_account_form(page, base_url)
    _fill(page, accounts.form_name, "Travel wallet", accounts.account_form)
    pick(page, accounts.form_currency, "EUR", scope=accounts.account_form)
    _submit(page, accounts.create_account, accounts.account_form)
    expect(to_playwright(page, accounts.account_form)).to_have_count(0)
    account_id = db_probe.account_id(db_path, "Travel wallet")
    assert (
        db_probe.scalar(db_path, "SELECT currency FROM accounts WHERE id = ?", account_id) == "EUR"
    )
    expect(to_playwright(page, accounts.row(account_id))).to_contain_text("Travel wallet")


@pytest.mark.skip(
    reason="T-UR08b: the new-account form currency combobox is not wired in the new shell"
)
def test_create_account_invalid_rerenders_form(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _open_new_account_form(page, base_url)
    # ``required`` blocks an empty name in the browser; whitespace passes it.
    _fill(page, accounts.form_name, "   ", accounts.account_form)
    pick(page, accounts.form_currency, "EUR", scope=accounts.account_form)
    _submit(page, accounts.create_account, accounts.account_form)
    expect(to_playwright(page, accounts.account_form)).to_have_count(1)
    expect(to_playwright(page, accounts.account_form)).to_contain_text("name required")
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM accounts") == 0


@pytest.mark.parametrize("entry", ["/settings?tab=categories"])
def test_create_category_submits_under_csp(
    live_server: tuple[str, Path], page: Page, entry: str
) -> None:
    # T-D150: the create form targeted ``table.ledger tbody``. ``/categories``
    # redirects to the Settings tab, the only page that hosts the form.
    base_url, db_path = live_server
    page.goto(f"{base_url}{entry}")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, settings.new_category).click()
    expect(to_playwright(page, settings.category_form)).to_be_visible()
    _fill(page, settings.category_name, "Pets", settings.category_form)
    _submit(page, settings.create_category, settings.category_form)
    expect(to_playwright(page, settings.category_form)).to_have_count(0)
    expect(to_playwright(page, settings.panel)).to_contain_text("Pets")
    assert db_probe.category_id(db_path, "Pets")


def test_create_category_blank_name_rerenders_form(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    page.goto(f"{base_url}/settings?tab=categories")
    to_playwright(page, settings.new_category).click()
    # ``required`` blocks an empty submit in the browser; whitespace passes it.
    _fill(page, settings.category_name, "   ", settings.category_form)
    _submit(page, settings.create_category, settings.category_form)
    expect(to_playwright(page, settings.category_form)).to_have_count(1)
    expect(to_playwright(page, settings.category_form)).to_contain_text("name required")
    assert db_probe.rows(db_path, "SELECT id FROM categories WHERE name = ''") == []
