"""E2E: reconcile an account, confirm adjustment transaction created."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import strip_id_prefix
from tests.e2e.forms import PANEL, add_happened, wait_for_htmx

pytestmark = pytest.mark.e2e


def test_reconcile_creates_adjustment_transaction(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, _db_path = live_server

    # Seed account with opening 100.00; add an expense of 40.00 → derived 60.00.
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": "Food", "direction": "expense"},
    ).ok

    page.goto(f"{base_url}/accounts")
    account_id = strip_id_prefix(
        page.locator("tr[id^='account-']").first.get_attribute("id"),
        "account-",
    )

    page.goto(f"{base_url}/ledger?view=actual")
    add_happened(
        page,
        category="Food",
        account="Checking",
        amount="40.00",
        day="2026-01-15",
        note="snack",
    )

    # Reconcile through the account row's form: bank says 70.00 -> +10.00 adjustment.
    page.goto(f"{base_url}/accounts")
    wait_for_htmx(page)
    page.locator(f"#account-{account_id}").get_by_role("button", name="Reconcile").click()
    panel = page.locator(PANEL)
    expect(panel).to_be_visible()
    panel.locator("input[name='actual_balance']").fill("70.00")
    with page.expect_response(
        lambda r: r.url.endswith("/reconcile") and r.request.method == "POST"
    ) as resp:
        panel.get_by_role("button", name="Record").click()
    assert resp.value.ok, resp.value.text()

    # Account card now shows 70.00.
    page.goto(f"{base_url}/accounts")
    checking_card = page.locator(f"#account-{account_id}")
    expect(checking_card).to_contain_text("70.00")

    # Transactions page should contain a 10.00 adjustment row (direction = adjustment).
    page.goto(f"{base_url}/transactions")
    expect(page.get_by_text("10.00").first).to_be_visible()
    expect(page.get_by_text("auto-reconciliation").first).to_be_visible()
