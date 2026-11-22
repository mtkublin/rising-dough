"""E2E: set a default budget, record spend, see remaining."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.forms import add_happened, wait_for_htmx
from tests.ui_map import plan
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_set_budget_shows_remaining_after_spend(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

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
    category_id = db_probe.category_id(db_path, "Groceries")
    assert (
        db_probe.scalar(
            db_path,
            "SELECT amount FROM budget_defaults WHERE category_id = ? AND deleted_at IS NULL",
            category_id,
        )
        == 50000
    )

    assert db_probe.txn_amounts(db_path, "weekly shop") == [12000]

    # Visit /budget for the same month: the summary table has a Groceries row.
    page.goto(f"{base_url}/budget?year=2026&month=10")
    groceries_row = to_playwright(page, plan.summary_row("Groceries")).first
    expect(groceries_row).to_contain_text("Groceries")
    # Budgeted
    expect(groceries_row).to_contain_text("500.00")
    # Spent
    expect(groceries_row).to_contain_text("120.00")
    # Remaining
    expect(groceries_row).to_contain_text("380.00")
