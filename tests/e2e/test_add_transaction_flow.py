"""E2E: create account → add transaction → see balance update."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import strip_id_prefix
from tests.e2e.forms import add_happened

pytestmark = pytest.mark.e2e


def test_add_transaction_updates_account_balance(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, _db_path = live_server

    # 1. Create a Checking account with opening_balance 100.00 PLN.
    create_resp = page.request.post(
        f"{base_url}/accounts",
        form={
            "name": "Checking",
            "currency": "PLN",
            "opening_balance": "100.00",
        },
    )
    assert create_resp.ok, create_resp.text()

    # 2. Create an expense category "Groceries".
    cat_resp = page.request.post(
        f"{base_url}/categories",
        form={"name": "Groceries", "direction": "expense"},
    )
    assert cat_resp.ok, cat_resp.text()

    # 3. Discover the created ids by scraping the accounts/categories pages.
    page.goto(f"{base_url}/accounts")
    expect(page.locator("text=Checking")).to_be_visible()
    # Opening balance renders as "100.00 zł".
    expect(page.get_by_text("100.00").first).to_be_visible()

    # Find the account_id by inspecting the row wrapper.
    account_el = page.locator("tr[id^='account-']").first
    account_id = strip_id_prefix(account_el.get_attribute("id"), "account-")

    # 4. Add a 20.00 expense through the real overlay form.
    page.goto(f"{base_url}/ledger?view=actual")
    add_happened(
        page,
        category="Groceries",
        account="Checking",
        amount="20.00",
        day="2026-01-15",
        note="milk",
    )

    # 5. Confirm balance on /accounts flipped to 80.00.
    page.goto(f"{base_url}/accounts")
    checking_card = page.locator(f"#account-{account_id}")
    expect(checking_card).to_contain_text("Checking")
    expect(checking_card).to_contain_text("80.00")
