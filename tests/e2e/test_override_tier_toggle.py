"""E2E under the prod CSP: override tier toggle works everywhere (T-D155, ADR-0113).

``budget-override.js`` used to load only from the Budget tab, so on /plan?tab=year
the "This month only / Every <Mon> / New default" control never changed state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e.conftest import strip_id_prefix

pytestmark = pytest.mark.e2e

_ACTIVE = "rd-segmented__item--active"


def _seed_budgeted(base_url: str, page: Page) -> str:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/settings?tab=categories")
    row = page.locator("[id^='category-']", has_text="Groceries").first
    category_id = strip_id_prefix(row.get_attribute("id"), "category-")
    assert page.request.post(
        f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}
    ).ok
    return category_id


def _tier(form: Locator, label: str) -> Locator:
    return form.locator("label.rd-segmented__item", has_text=label)


def _assert_toggle(form: Locator) -> None:
    hint = form.locator("[data-override-hint-tail]")
    expect(_tier(form, "This month only")).to_have_class(f"rd-segmented__item {_ACTIVE}")
    _tier(form, "Every").click()
    expect(_tier(form, "Every")).to_have_class(f"rd-segmented__item {_ACTIVE}")
    expect(_tier(form, "This month only")).to_have_class("rd-segmented__item")
    expect(hint).to_contain_text("replaces default every")
    _tier(form, "New default").click()
    expect(_tier(form, "New default")).to_have_class(f"rd-segmented__item {_ACTIVE}")
    expect(_tier(form, "Every")).to_have_class("rd-segmented__item")
    expect(hint).to_have_text("replaces the default")


def test_tier_toggle_on_plan_year_popover(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    category_id = _seed_budgeted(base_url, page)
    page.goto(f"{base_url}/plan?tab=year")
    page.locator(f"#yc-{category_id}-3 .rd-plan-year__cell-btn").click()
    form = page.locator(f"#yc-{category_id}-3 form[data-override-form]")
    expect(form).to_be_visible()
    _assert_toggle(form)


def test_recurring_override_saved_from_plan_year(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    category_id = _seed_budgeted(base_url, page)
    page.goto(f"{base_url}/plan?tab=year")
    page.locator(f"#yc-{category_id}-3 .rd-plan-year__cell-btn").click()
    form = page.locator(f"#yc-{category_id}-3 form[data-override-form]")
    _tier(form, "Every").click()
    form.locator("input[name='amount']").fill("321.00")
    with page.expect_response(
        lambda r: r.url.endswith(f"/budget/rules/{category_id}/overrides")
    ) as resp:
        form.get_by_role("button", name="Save").click()
    assert resp.value.ok
    # The page reloads and the recurring override shows in the March cell.
    expect(page.locator(f"#yc-{category_id}-3")).to_contain_text("321")
    expect(page.locator(f"#yc-{category_id}-3 form")).to_have_count(0)


def test_tier_toggle_on_budget_tab_inline(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    category_id = _seed_budgeted(base_url, page)
    page.goto(f"{base_url}/plan?tab=budget")
    page.locator(f"[data-override-open='{category_id}']").click()
    form = page.locator(f"#override-slot-{category_id} form[data-override-form]")
    expect(form).to_be_visible()
    _assert_toggle(form)
