"""E2E under the prod CSP: the buttons that broke in prod v3.0.1 (T-D140c, ADR-0113).

The ``page`` fixture serves every HTML response with the CSP parsed from
``Caddyfile.tpl`` and fails the test on any CSP violation, so these tests
only need to drive the UI and assert its visible result.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e.conftest import strip_id_prefix

pytestmark = pytest.mark.e2e


def _seed(base_url: str, page: Page, category: str = "Groceries") -> tuple[str, str]:
    """Create one account + one expense category; return (account_id, category_id)."""
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": category, "direction": "expense"},
    ).ok
    page.goto(f"{base_url}/accounts")
    account_id = strip_id_prefix(
        page.locator("tr[id^='account-']").first.get_attribute("id"), "account-"
    )
    page.goto(f"{base_url}/categories")
    row = page.locator("[id^='category-']", has_text=category).first
    return account_id, strip_id_prefix(row.get_attribute("id"), "category-")


def _pick(page: Page, name: str, label: str) -> None:
    """Choose ``label`` in the combobox backing the hidden input ``name``."""
    combo = page.locator("[data-combobox]", has=page.locator(f"input[name='{name}']"))
    combo.locator("[data-combobox-input]").click()
    combo.locator("[role='option']", has_text=label).first.click()


def _open_add_slide_over(page: Page, base_url: str, route: str) -> Locator:
    page.goto(f"{base_url}{route}")
    assert page.evaluate("typeof window.htmx") == "object"
    page.locator("[data-rd-add]:visible").first.click()
    form = page.locator("#txn-form")
    expect(form).to_be_visible()
    return form


def test_add_slide_over_on_today_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    form = _open_add_slide_over(page, base_url, "/today")
    # Combobox + close behaviour are static JS and must work under the CSP.
    _pick(page, "category_id", "Groceries")
    _pick(page, "account_id", "Checking")
    expect(form.locator("input[name='category_id']")).not_to_have_value("")
    page.get_by_role("button", name="Cancel").click()
    expect(form).to_have_count(0)


def test_add_from_today_submits_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    form = _open_add_slide_over(page, base_url, "/today")
    _pick(page, "category_id", "Groceries")
    _pick(page, "account_id", "Checking")
    form.locator("input[name='amount']").fill("12.34")
    form.locator("input[name='description']").fill("today-added")
    form.get_by_role("button", name="Add entry").click()
    # Overlay closes and Today reloads: the 500.00 opening balance drops by 12.34.
    expect(page.locator("#txn-form")).to_have_count(0)
    expect(page.locator(".rd-netcard__rows")).to_contain_text("487.66")
    page.goto(f"{base_url}/ledger?view=actual")
    expect(page.get_by_text("today-added").first).to_be_visible()


def test_add_from_today_invalid_amount_rerenders_form(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    form = _open_add_slide_over(page, base_url, "/today")
    _pick(page, "category_id", "Groceries")
    _pick(page, "account_id", "Checking")
    form.locator("input[name='amount']").fill("0")
    form.get_by_role("button", name="Add entry").click()
    expect(page.locator("#txn-form")).to_have_count(1)
    expect(page.locator("#txn-form")).to_contain_text("amount")


def test_add_slide_over_on_ledger_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    form = _open_add_slide_over(page, base_url, "/ledger")
    _pick(page, "category_id", "Groceries")
    _pick(page, "account_id", "Checking")
    form.locator("input[name='amount']").fill("12.34")
    form.locator("input[name='description']").fill("csp-added")
    form.get_by_role("button", name="Add entry").click()
    expect(page.locator("#txn-table").get_by_text("csp-added").first).to_be_visible()


def test_promote_on_today_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    account_id, category_id = _seed(base_url, page)
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

    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    row = page.locator("#upcoming-root", has_text="csp-promote")
    row.get_by_role("button", name="Promote").first.click()
    page.get_by_role("button", name="Confirm").click()
    # The promoted planned item leaves Upcoming and lands in the ledger.
    expect(page.locator("#upcoming-root").get_by_text("csp-promote")).to_have_count(0)
    page.goto(f"{base_url}/ledger?view=actual")
    expect(page.get_by_text("csp-promote").first).to_be_visible()


def test_override_on_plan_budget_under_csp(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _, category_id = _seed(base_url, page)
    assert page.request.post(
        f"{base_url}/budget/defaults/{category_id}", form={"amount": "500.00"}
    ).ok

    page.goto(f"{base_url}/plan?tab=budget")
    assert page.evaluate("typeof window.htmx") == "object"
    page.locator(f"[data-override-open='{category_id}']").click()
    slot = page.locator(f"#override-slot-{category_id}")
    slot.get_by_text("New default").click()
    amount = slot.locator("input[name='amount']")
    expect(amount).to_be_visible()
    amount.fill("321.00")
    slot.get_by_role("button", name="Save").click()
    # Slot closes and the budget region re-renders with the override applied.
    expect(slot.locator("input[name='amount']")).to_have_count(0)
    expect(page.locator("#plan-budget")).to_contain_text("321.00")
