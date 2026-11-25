"""Accounts page journeys on either target (T-UR08, ADR-0106; ADR-0107).

``--target=app`` loads the live page (seeded through the app's own routes);
``--target=mockup`` runs the same names against ``pages/accounts.html`` and
``pages/accounts--empty.html``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def _seed_accounts(journey: Journey) -> None:
    """App target only: one asset and one credit card with a limit (the page has rows)."""
    if journey.target != "app":
        return
    page: Any = journey.page
    forms = (
        {"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
        {
            "name": "Visa",
            "currency": "PLN",
            "opening_balance": "-1234.56",
            "is_liability": "on",
            "credit_limit": "5000.00",
        },
    )
    for form in forms:
        resp = page.request.post(f"{journey.base_url}/accounts", form=form)
        assert resp.ok, resp.status


def test_accounts_shows_hero_rows_and_new_account(journey: Journey) -> None:
    accounts = journey.ui("accounts")
    _seed_accounts(journey)
    journey.goto("/accounts")
    page: Any = journey.page
    to_playwright(page, accounts.heading).wait_for(state="visible")
    to_playwright(page, accounts.any_row).first.wait_for(state="visible")
    to_playwright(page, accounts.new_account_button).wait_for(state="visible")
    to_playwright(page, accounts.reconcile_button(1)).first.wait_for(state="visible")


def test_accounts_credit_card_row_shows_the_utilisation_line(journey: Journey) -> None:
    accounts = journey.ui("accounts")
    _seed_accounts(journey)
    journey.goto("/accounts")
    page: Any = journey.page
    to_playwright(page, accounts.credit_utilisation).first.wait_for(state="visible")


def test_accounts_empty_state_offers_a_new_account(journey: Journey) -> None:
    accounts = journey.ui("accounts")
    journey.goto("/accounts?state=empty")
    page: Any = journey.page
    to_playwright(page, accounts.heading).wait_for(state="visible")
    to_playwright(page, accounts.new_account_cta).wait_for(state="visible")
    assert to_playwright(page, accounts.any_row).count() == 0


def test_accounts_reconcile_opens_the_overlay(journey: Journey) -> None:
    accounts = journey.ui("accounts")
    _seed_accounts(journey)
    journey.goto("/accounts")
    page: Any = journey.page
    to_playwright(page, accounts.reconcile_button(1)).first.click()
    if journey.target == "mockup":
        page.wait_for_url("**/pages/overlays/reconcile*.html")
    else:
        to_playwright(page, accounts.reconcile_dialog).wait_for(state="visible")
