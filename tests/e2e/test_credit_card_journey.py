"""E2E — Phase 7 credit-card journey (ADR-0024).

Covers the full user flow: create a Visa credit-card account, confirm the
utilization strip on the account card, post a within-limit expense, confirm
Assets / Liabilities / Net worth split updates on the dashboard, overshoot
the limit (soft-only), confirm the over-limit badge renders, and pay the
balance down to zero via a transit from a bank account.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import accounts, shell
from tests.ui_map.locator import to_playwright

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skip(
        reason="v1 credit-strip + fortune-split rendered on Accounts card — "
        "superseded by Rising Dough table (ADR-0051 §6); re-enable after Phase 7"
    ),
]


def _create_account(
    page: Page,
    base_url: str,
    db_path: Path,
    *,
    name: str,
    currency: str,
    opening_balance: str = "0",
    is_liability: bool = False,
    credit_limit: str = "",
    type_: str = "",
) -> str:
    form: dict[str, str | float | bool] = {
        "name": name,
        "currency": currency,
        "opening_balance": opening_balance,
        "type": type_,
    }
    if is_liability:
        form["is_liability"] = "on"
        form["credit_limit"] = credit_limit
    resp = page.request.post(f"{base_url}/accounts", form=form)
    assert resp.ok, resp.text()
    return str(db_probe.account_id(db_path, name))


def _create_category(page: Page, base_url: str, db_path: Path, *, name: str, direction: str) -> str:
    resp = page.request.post(f"{base_url}/categories", form={"name": name, "direction": direction})
    assert resp.ok, resp.text()
    return str(db_probe.category_id(db_path, name))


def test_credit_card_full_journey(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

    # 1. Seed: a bank account, a Visa credit-card account, a Groceries category.
    bank_id = _create_account(
        page, base_url, db_path, name="Bank", currency="PLN", opening_balance="200.00", type_="bank"
    )
    visa_id = _create_account(
        page,
        base_url,
        db_path,
        name="Visa",
        currency="PLN",
        is_liability=True,
        credit_limit="100.00",
        type_="credit_card",
    )
    groc_id = _create_category(page, base_url, db_path, name="Groceries", direction="expense")

    # 2. Visa card renders the credit strip with 0% used.
    page.goto(f"{base_url}/accounts")
    visa_card = to_playwright(page, accounts.row(int(visa_id)))
    expect(visa_card).to_contain_text("Credit card")
    expect(visa_card).to_contain_text("100.00")
    expect(visa_card).to_contain_text("0%")

    # 3. Accounts page renders the three-line fortune split.
    page.goto(f"{base_url}/accounts")
    main = to_playwright(page, shell.main)
    expect(main).to_contain_text("Assets")
    expect(main).to_contain_text("Liabilities")
    expect(main).to_contain_text("Net worth")

    # 4. Add a 50.00 expense on the Visa account — within-limit.
    resp = page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": "2026-01-15",
            "category_id": groc_id,
            "account_id": visa_id,
            "amount": "50.00",
            "description": "within limit",
        },
    )
    assert resp.ok, resp.text()

    # 5. Visa card updates — 50% used, no over-limit badge.
    page.goto(f"{base_url}/accounts")
    visa_card = to_playwright(page, accounts.row(int(visa_id)))
    expect(visa_card).to_contain_text("50.00")
    expect(visa_card).to_contain_text("50%")
    expect(visa_card).not_to_contain_text("Over limit by")

    # 6. Overshoot: add a 200.00 expense (above the 100.00 limit, soft only).
    resp = page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": "2026-01-16",
            "category_id": groc_id,
            "account_id": visa_id,
            "amount": "200.00",
            "description": "overshoot",
        },
    )
    assert resp.ok, resp.text()  # soft — not rejected

    # 7. Over-limit badge renders.
    page.goto(f"{base_url}/accounts")
    visa_card = to_playwright(page, accounts.row(int(visa_id)))
    expect(visa_card).to_contain_text("Over limit by")

    # 8. Pay off: transit 250.00 from Bank → Visa, zeroing the Visa balance.
    transit_id = db_probe.category_id(db_path, "Transit")
    resp = page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": "2026-01-17",
            "category_id": str(transit_id),
            "account_id": bank_id,
            "dest_account_id": visa_id,
            "amount": "250.00",
            "description": "payoff",
        },
    )
    assert resp.ok, resp.text()

    # 9. Visa returns to 0% used, no over-limit badge.
    page.goto(f"{base_url}/accounts")
    visa_card = to_playwright(page, accounts.row(int(visa_id)))
    expect(visa_card).to_contain_text("0%")
    expect(visa_card).not_to_contain_text("Over limit by")
