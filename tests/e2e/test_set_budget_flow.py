"""E2E: set a default budget, record spend, see remaining."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.forms import add_happened
from tests.ui_map import plan_budget, plan_year
from tests.ui_map.locator import role, to_playwright

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

    # Record a 120.00 expense in a known month to query the budget tab deterministically.
    page.goto(f"{base_url}/ledger?view=actual")
    add_happened(
        page,
        category="Groceries",
        account="Checking",
        amount="120.00",
        day="2026-10-15",
        note="weekly shop",
    )

    # Set a default budget of 500.00 from the year tab's "without a budget" chip: the dialog
    # opens on the "new default" scope.
    page.goto(f"{base_url}/plan?tab=year&year=2026")
    # The disclosure is a <details> summary (no button role in the accessibility tree).
    page.get_by_text(re.compile(r"without a budget$")).click()
    to_playwright(page, plan_year.unbudgeted("Groceries")).click()
    dialog = role("dialog", re.compile(r"^override budget · Groceries"))
    to_playwright(page, plan_year.amount(dialog)).fill("500.00")
    with page.expect_response(
        lambda r: "/budget/rules/" in r.url and r.request.method == "POST"
    ) as resp:
        to_playwright(page, plan_year.save(dialog)).click()
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

    # The budget tab of the same month shows budgeted, spent and what is left.
    page.goto(f"{base_url}/plan?tab=budget&year=2026&month=10")
    cells = to_playwright(page, plan_budget.row_cells("Groceries"))
    expect(cells.nth(2)).to_have_text("120.00 / 500.00")
    expect(cells.nth(3)).to_have_text("left 380.00")
