"""E2E under the prod CSP: override tier toggle works everywhere (T-D155, ADR-0113).

``budget-override.js`` used to load only from the Budget tab, so on /plan?tab=year
the "This month only / Every <Mon> / New default" control never changed state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import plan
from tests.ui_map.locator import Locator as UiLocator, to_playwright

pytestmark = pytest.mark.e2e

_YEAR_CELL_MONTH = 3  # March


def _seed_budgeted(base_url: str, db_path: Path, page: Page) -> int:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    category_id = db_probe.category_id(db_path, "Groceries")
    assert page.request.post(
        f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}
    ).ok
    return category_id


def _assert_toggle(page: Page, scope: UiLocator) -> None:
    """Walk the tier radios inside ``scope``; the hint text follows the selection."""
    one_off = to_playwright(page, plan.tier_one_off.inside(scope))
    every = to_playwright(page, plan.tier_recurring.inside(scope))
    new_default = to_playwright(page, plan.tier_default.inside(scope))
    form_text = to_playwright(page, scope)
    expect(one_off).to_be_checked()
    every.dispatch_event("click")
    expect(every).to_be_checked()
    expect(one_off).not_to_be_checked()
    expect(form_text).to_contain_text("replaces default every")
    new_default.dispatch_event("click")
    expect(new_default).to_be_checked()
    expect(every).not_to_be_checked()
    expect(form_text).to_contain_text("replaces the default")


def test_tier_toggle_on_plan_year_popover(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    category_id = _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=year")
    cell = plan.year_cell(category_id, _YEAR_CELL_MONTH)
    to_playwright(page, plan.year_cell_open(category_id, _YEAR_CELL_MONTH)).click()
    expect(to_playwright(page, plan.override_amount.inside(cell))).to_be_visible()
    _assert_toggle(page, cell)


def test_recurring_override_saved_from_plan_year(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    category_id = _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=year")
    cell = plan.year_cell(category_id, _YEAR_CELL_MONTH)
    to_playwright(page, plan.year_cell_open(category_id, _YEAR_CELL_MONTH)).click()
    to_playwright(page, plan.tier_recurring.inside(cell)).dispatch_event("click")
    to_playwright(page, plan.override_amount.inside(cell)).fill("321.00")
    with page.expect_response(
        lambda r: r.url.endswith(f"/budget/rules/{category_id}/overrides")
    ) as resp:
        to_playwright(page, plan.override_save.inside(cell)).click()
    assert resp.value.ok
    # The page reloads and the recurring override shows in the March cell.
    expect(to_playwright(page, cell)).to_contain_text("321")
    expect(to_playwright(page, plan.override_amount.inside(cell))).to_have_count(0)
    assert (
        db_probe.scalar(
            db_path,
            "SELECT amount FROM budget_recurring_overrides"
            " WHERE category_id = ? AND month = ? AND deleted_at IS NULL",
            category_id,
            _YEAR_CELL_MONTH,
        )
        == 32100
    )


def test_tier_toggle_on_budget_tab_inline(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    category_id = _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=budget")
    to_playwright(page, plan.override_button("Groceries")).click()
    slot = plan.override_slot(category_id)
    expect(to_playwright(page, plan.override_amount.inside(slot))).to_be_visible()
    _assert_toggle(page, slot)
