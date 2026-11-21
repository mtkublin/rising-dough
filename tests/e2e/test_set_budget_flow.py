"""E2E: set a default budget, record spend, see remaining."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
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

    account_id = db_probe.account_id(db_path, "Checking")
    category_id = db_probe.category_id(db_path, "Groceries")

    # Set a default budget of 500.00 for Groceries.
    assert page.request.post(
        f"{base_url}/budget/defaults/{category_id}",
        form={"amount": "500.00"},
    ).ok
    assert (
        db_probe.scalar(
            db_path,
            "SELECT amount FROM budget_defaults WHERE category_id = ? AND deleted_at IS NULL",
            category_id,
        )
        == 50000
    )

    # Record a 120.00 expense in a known month to query /budget deterministically.
    assert page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": "2026-10-15",
            "category_id": str(category_id),
            "account_id": str(account_id),
            "amount": "120.00",
            "description": "weekly shop",
        },
    ).ok

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
