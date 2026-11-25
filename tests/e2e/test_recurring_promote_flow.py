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

from tests.e2e import db_probe
from tests.e2e.forms import PANEL, wait_for_htmx
from tests.e2e.ui_actions import submit_ok
from tests.ui_map import ledger
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_recurring_rule_and_planned_promote_cycle(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

    # Seed account + category.
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": "Rent", "direction": "expense"},
    ).ok

    account_id = db_probe.account_id(db_path, "Checking")
    category_id = db_probe.category_id(db_path, "Rent")

    # Create a monthly recurring rule starting 2026-01-15 for 50.00. The rule
    # surfaces only in the Recurring tab now (T-119).
    assert page.request.post(
        f"{base_url}/recurring",
        form={
            "cadence": "monthly",
            "start_date": "2026-01-15",
            "category_id": str(category_id),
            "account_id": str(account_id),
            "default_amount": "50.00",
            "default_description": "rent",
        },
    ).ok

    # Planned tab excludes virtual rows post-T-119.
    page.goto(
        f"{base_url}/ledger?view=planned&date_from=2026-01-01&date_to=2026-03-31",
    )
    expect(to_playwright(page, ledger.any_virtual_planned_row)).to_have_count(0)

    # Create a one-off planned so promotion is a real router call.
    planned_resp = page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": "2026-01-20",
            "category_id": str(category_id),
            "account_id": str(account_id),
            "amount": "25.00",
            "description": "one-off",
        },
    )
    assert planned_resp.ok, planned_resp.text()

    # The persisted row shows in the Planned tab.
    planned_id = db_probe.planned_id(db_path, "one-off")
    page.goto(
        f"{base_url}/ledger?view=planned&date_from=2026-01-01&date_to=2026-03-31",
    )
    expect(to_playwright(page, ledger.planned_row(planned_id))).to_be_visible()

    # Promote through the row's promote dialog (link opens #modal-root, T-UR24), edited amount.
    wait_for_htmx(page)
    to_playwright(page, ledger.planned_promote(planned_id)).click()
    expect(to_playwright(page, PANEL)).to_be_visible()
    to_playwright(page, ledger.overlay_field(ledger.field_date)).fill("2026-01-22")
    to_playwright(page, ledger.overlay_field(ledger.field_amount)).fill("27.50")
    to_playwright(page, ledger.overlay_field(ledger.field_note)).fill("promoted one-off")
    # The typed values must still be in the form when it posts (a re-render would reset them).
    expect(to_playwright(page, ledger.overlay_field(ledger.field_amount))).to_have_value("27.50")
    expect(to_playwright(page, ledger.overlay_field(ledger.field_note))).to_have_value(
        "promoted one-off"
    )
    submit_ok(page, ledger.overlay_promote, path_suffix="/promote")

    # DB: the planned row points at the new transaction, with the edited amount.
    assert db_probe.txn_amounts(db_path, "promoted one-off") == [2750]
    assert db_probe.scalar(
        db_path, "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?", planned_id
    )

    # Verify the transaction appears on the unified ledger (Phase 6 — T-064
    # collapsed /transactions, /planned, /recurring into /ledger?view=…).
    page.goto(f"{base_url}/ledger?view=actual")
    expect(to_playwright(page, ledger.table_container)).to_contain_text("27.50")
