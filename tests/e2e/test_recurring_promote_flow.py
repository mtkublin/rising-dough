"""E2E: add recurring rule → add one-off planned → promote the planned row.

Post-T-119 (ADR-0038): the Planned tab no longer surfaces virtual
occurrences; recurring rules get their own promote-and-advance affordance
under /ledger?view=recurring. This test now exercises the persisted
planned promotion path only (recurring promotion lives in a dedicated
e2e once T-122 ships the Ledger row actions).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import strip_id_prefix
from tests.e2e.forms import PANEL, wait_for_htmx

pytestmark = pytest.mark.e2e


def test_recurring_rule_and_planned_promote_cycle(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, _db_path = live_server

    # Seed account + category.
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": "Rent", "direction": "expense"},
    ).ok

    page.goto(f"{base_url}/accounts")
    account_id = strip_id_prefix(
        page.locator("tr[id^='account-']").first.get_attribute("id"),
        "account-",
    )
    page.goto(f"{base_url}/categories")
    rent_row = page.locator("[id^='category-']", has_text="Rent").first
    category_id = strip_id_prefix(rent_row.get_attribute("id"), "category-")

    # Create a monthly recurring rule starting 2026-01-15 for 50.00. The rule
    # surfaces only in the Recurring tab now (T-119).
    assert page.request.post(
        f"{base_url}/recurring",
        form={
            "cadence": "monthly",
            "start_date": "2026-01-15",
            "category_id": category_id,
            "account_id": account_id,
            "default_amount": "50.00",
            "default_description": "rent",
        },
    ).ok

    # Planned tab excludes virtual rows post-T-119.
    page.goto(
        f"{base_url}/ledger?view=planned&date_from=2026-01-01&date_to=2026-03-31",
    )
    expect(page.locator("tr[id^='planned-v-']")).to_have_count(0)

    # Create a one-off planned so promotion is a real router call.
    planned_resp = page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": "2026-01-20",
            "category_id": category_id,
            "account_id": account_id,
            "amount": "25.00",
            "description": "one-off",
        },
    )
    assert planned_resp.ok, planned_resp.text()

    page.goto(
        f"{base_url}/ledger?view=planned&date_from=2026-01-01&date_to=2026-03-31",
    )
    persisted_el = page.locator("tr[id^='planned-p-']").first

    # Promote through the row's slide-over form with an edited amount.
    wait_for_htmx(page)
    persisted_el.get_by_role("button", name="Promote").click()
    panel = page.locator(PANEL)
    expect(panel).to_be_visible()
    panel.locator("input[name='operation_date']").fill("2026-01-22")
    panel.locator("input[name='amount']").fill("27.50")
    panel.locator("input[name='description']").fill("promoted one-off")
    with page.expect_response(
        lambda r: r.url.endswith("/promote") and r.request.method == "POST"
    ) as resp:
        panel.get_by_role("button", name="Promote").click()
    assert resp.value.ok, resp.value.text()

    # Verify the transaction appears on the unified ledger (Phase 6 — T-064
    # collapsed /transactions, /planned, /recurring into /ledger?view=…).
    page.goto(f"{base_url}/ledger?view=actual")
    expect(page.get_by_text("27.50").first).to_be_visible()
