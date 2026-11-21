"""E2E: set a default budget, record spend, see remaining."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.forms import add_happened, wait_for_htmx

pytestmark = pytest.mark.e2e


def test_set_budget_shows_remaining_after_spend(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, _db_path = live_server

    # Seed: one account + Groceries category.
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": "Groceries", "direction": "expense"},
    ).ok

    # Record a 120.00 expense in a known month to query /budget deterministically.
    page.goto(f"{base_url}/ledger?view=actual")
    add_happened(
        page,
        category="Groceries",
        account="Checking",
        amount="120.00",
        day="2026-10-15",
        note="weekly shop",
    )

    # Set a default budget of 500.00 for Groceries through the inline rule form.
    page.goto(f"{base_url}/budget?year=2026&month=10")
    wait_for_htmx(page)
    page.get_by_label("Default budget for Groceries").fill("500.00")
    with page.expect_response(
        lambda r: "/budget/defaults/" in r.url and r.request.method == "POST"
    ) as resp:
        page.locator("form.budget-rule-form", has_text="Save").get_by_role(
            "button", name="Save"
        ).click()
    assert resp.value.ok, resp.value.text()

    # Visit /budget for the same month. Phase 9 (T-100/T-101) refactored
    # the summary surface: `#budget-summary` is a `<section>` wrapping a
    # `<table class="budget-row-table">`; the id no longer sits on the table.
    page.goto(f"{base_url}/budget?year=2026&month=10")
    groceries_row = page.locator(
        "#budget-summary table.budget-row-table tr",
        has_text="Groceries",
    ).first
    expect(groceries_row).to_contain_text("Groceries")
    # Budgeted
    expect(groceries_row).to_contain_text("500.00")
    # Spent
    expect(groceries_row).to_contain_text("120.00")
    # Remaining
    expect(groceries_row).to_contain_text("380.00")
