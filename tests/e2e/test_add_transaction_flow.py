"""E2E: create account → add transaction → see balance update."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.forms import add_happened
from tests.ui_map import accounts
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_add_transaction_updates_account_balance(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

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

    # 3. Look the created ids up in the scratch DB.
    account_id = db_probe.account_id(db_path, "Checking")
    page.goto(f"{base_url}/accounts")
    checking = to_playwright(page, accounts.row(account_id))
    expect(checking).to_contain_text("Checking")
    # Opening balance renders as "100.00 zł".
    expect(checking).to_contain_text("100.00")

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
    assert db_probe.txn_amounts(db_path, "milk") == [2000]

    # 5. Confirm balance on /accounts flipped to 80.00.
    page.goto(f"{base_url}/accounts")
    checking_card = to_playwright(page, accounts.row(account_id))
    expect(checking_card).to_contain_text("Checking")
    expect(checking_card).to_contain_text("80.00")
