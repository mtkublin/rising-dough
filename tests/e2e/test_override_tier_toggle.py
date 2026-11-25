"""E2E under the prod CSP: the override scope toggle works from every entry (T-D155, ADR-0113).

The scope control ("this month only / every <month> / new default") used to depend on a script that
loaded on one tab only. The dialog (T-UR11b) is plain radios, so it must switch on the year tab
and from the budget row menu alike, and a recurring save from the year grid lands in the cell.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import plan_budget, plan_year
from tests.ui_map.locator import Locator as UiLocator, to_playwright

pytestmark = pytest.mark.e2e

_MARCH = 3
_LABELS = ("this month only", "every march", "new default")


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


def _assert_toggle(page: Page, dialog: UiLocator) -> None:
    """Walk the scope radios of ``dialog``; exactly the clicked one is checked."""
    one_off, every, new_default = (
        to_playwright(page, plan_year.tier(dialog, label)) for label in _LABELS
    )
    expect(one_off).to_be_checked()
    every.dispatch_event("click")
    expect(every).to_be_checked()
    expect(one_off).not_to_be_checked()
    new_default.dispatch_event("click")
    expect(new_default).to_be_checked()
    expect(every).not_to_be_checked()


def test_tier_toggle_on_plan_year_dialog(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=year&year=2026")
    to_playwright(page, plan_year.cell("Groceries", "March")).click()
    dialog = plan_year.dialog("Groceries", "Mar 2026")
    expect(to_playwright(page, plan_year.amount(dialog))).to_be_visible()
    _assert_toggle(page, dialog)


def test_recurring_override_saved_from_plan_year(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    category_id = _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=year&year=2026")
    to_playwright(page, plan_year.cell("Groceries", "March")).click()
    dialog = plan_year.dialog("Groceries", "Mar 2026")
    to_playwright(page, plan_year.tier(dialog, "every march")).dispatch_event("click")
    to_playwright(page, plan_year.amount(dialog)).fill("321.00")
    with page.expect_response(
        lambda r: r.url.endswith(f"/budget/rules/{category_id}/overrides")
    ) as resp:
        to_playwright(page, plan_year.save(dialog)).click()
    assert resp.value.ok
    # The dialog closes and the grid reloads with the recurring override in the March cell.
    expect(to_playwright(page, dialog)).to_have_count(0)
    expect(to_playwright(page, plan_year.cell("Groceries", "March"))).to_have_text("↻ 321.00")
    assert (
        db_probe.scalar(
            db_path,
            "SELECT amount FROM budget_recurring_overrides"
            " WHERE category_id = ? AND month = ? AND deleted_at IS NULL",
            category_id,
            _MARCH,
        )
        == 32100
    )


def test_tier_toggle_on_budget_tab_dialog(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed_budgeted(base_url, db_path, page)
    page.goto(f"{base_url}/plan?tab=budget&year=2026&month={_MARCH}")
    to_playwright(page, plan_budget.row_menu_button("Groceries")).click()
    to_playwright(page, plan_budget.override_item("Groceries")).click()
    dialog = plan_year.dialog("Groceries", "Mar 2026")
    expect(to_playwright(page, plan_year.amount(dialog))).to_be_visible()
    _assert_toggle(page, dialog)
