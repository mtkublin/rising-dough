"""E2E under the prod CSP: edit / override / promote paths (T-D151, ADR-0113).

These forms used to target ledger row ids, so they did nothing from Today,
left the slide-over open after a save, and let a 422 replace the ledger row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e import db_probe
from tests.ui_map import edit_dialogs, entries, ledger, shell, today
from tests.ui_map.locator import Locator as UiLocator, to_playwright

pytestmark = pytest.mark.e2e


def _today() -> datetime:
    return datetime.now(tz=UTC)


def _seed(base_url: str, db_path: Path, page: Page) -> tuple[str, str]:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    return str(db_probe.account_id(db_path, "Checking")), str(
        db_probe.category_id(db_path, "Groceries")
    )


def _rule(base_url: str, page: Page, ids: tuple[str, str], cadence: str = "monthly") -> None:
    assert page.request.post(
        f"{base_url}/recurring",
        form={
            "cadence": cadence,
            "start_date": (_today() + timedelta(days=2)).date().isoformat(),
            "category_id": ids[1],
            "account_id": ids[0],
            "default_amount": "50.00",
            "default_description": "edit-rule",
        },
    ).ok


def _planned(base_url: str, page: Page, ids: tuple[str, str]) -> None:
    assert page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": (_today() + timedelta(days=2)).date().isoformat(),
            "category_id": ids[1],
            "account_id": ids[0],
            "amount": "25.00",
            "description": "edit-planned",
        },
    ).ok


def _ledger(base_url: str, view: str) -> str:
    lo = (_today() - timedelta(days=30)).date().isoformat()
    hi = (_today() + timedelta(days=400)).date().isoformat()
    return f"{base_url}/ledger?view={view}&date_from={lo}&date_to={hi}"


def _panel(page: Page) -> Locator:
    result: Locator = to_playwright(page, shell.slideover)
    return result


def _kebab_item(page: Page, row: UiLocator, name: str) -> None:
    to_playwright(page, ledger.row_kebab(row)).click()
    to_playwright(page, ledger.row_menu_item(row, name)).click()


def _override_from_today(page: Page, row: UiLocator) -> None:
    """Open the row menu of an Upcoming row and pick "override" (a link that opens the dialog)."""
    to_playwright(page, edit_dialogs.row_menu_button(row)).click()
    to_playwright(page, edit_dialogs.override_item(row)).click()


def _save_override(page: Page, dialog: UiLocator, amount: str) -> None:
    to_playwright(page, edit_dialogs.hero_amount(dialog)).fill(amount)
    to_playwright(page, edit_dialogs.save(dialog)).click()


def test_today_override_recurring_saves_and_closes(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _rule(base_url, page, _seed(base_url, db_path, page))
    row = today.upcoming_recurring(db_probe.rule_id(db_path, "edit-rule"))
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    _override_from_today(page, row)
    dialog = edit_dialogs.occurrence_dialog("Groceries")
    expect(to_playwright(page, dialog)).to_be_visible()
    # the dialog opens on the occurrence the row names, with the rule's amount
    expect(to_playwright(page, edit_dialogs.hero_amount(dialog))).to_have_value("50.00")
    _save_override(page, dialog, "77.00")
    expect(to_playwright(page, dialog)).to_have_count(0)
    assert db_probe.scalar(db_path, "SELECT amount_override FROM recurring_rule_overrides") == 7700
    # Upcoming refetches itself: the row now shows the override
    expect(to_playwright(page, row)).to_contain_text("77.00")


def test_today_override_planned_saves_and_closes(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _planned(base_url, page, _seed(base_url, db_path, page))
    row = today.upcoming_planned(db_probe.planned_id(db_path, "edit-planned"))
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    _override_from_today(page, row)
    dialog = edit_dialogs.planned_dialog("Groceries")
    expect(to_playwright(page, dialog)).to_be_visible()
    expect(to_playwright(page, edit_dialogs.hero_amount(dialog))).to_have_value("25.00")
    _save_override(page, dialog, "33.00")
    expect(to_playwright(page, dialog)).to_have_count(0)
    assert (
        db_probe.scalar(
            db_path, "SELECT amount FROM planned_transactions WHERE description = 'edit-planned'"
        )
        == 3300
    )
    expect(to_playwright(page, row)).to_contain_text("33.00")


def test_txn_edit_dialog_closes_and_row_updates(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    account_id, category_id = _seed(base_url, db_path, page)
    assert page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": _today().date().isoformat(),
            "category_id": category_id,
            "account_id": account_id,
            "amount": "12.34",
            "description": "edit-txn",
        },
    ).ok
    tx = ledger.row(db_probe.txn_id(db_path, "edit-txn"))
    page.goto(f"{base_url}/transactions/{db_probe.txn_id(db_path, 'edit-txn')}/edit")
    expect(to_playwright(page, entries.edit_dialog)).to_be_visible()
    to_playwright(page, entries.edit_amount).fill("99.00")
    to_playwright(page, entries.edit_save).click()
    expect(to_playwright(page, entries.edit_dialog)).to_have_count(0)
    assert db_probe.txn_amounts(db_path, "edit-txn") == [9900]
    page.goto(_ledger(base_url, "actual"))
    expect(to_playwright(page, tx)).to_contain_text("99.00")


def test_ledger_planned_promote_closes(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _planned(base_url, page, _seed(base_url, db_path, page))
    page.goto(_ledger(base_url, "planned"))
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(
        page, ledger.planned_promote(db_probe.planned_id(db_path, "edit-planned"))
    ).click()
    expect(_panel(page)).to_be_visible()
    to_playwright(page, entries.promote_submit).click()
    expect(_panel(page)).to_have_count(0)
    assert db_probe.txn_amounts(db_path, "edit-planned") == [2500]
    page.goto(_ledger(base_url, "actual"))
    expect(to_playwright(page, ledger.table_container)).to_contain_text("edit-planned")


def test_override_invalid_month_shows_error_in_the_dialog(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _rule(base_url, page, _seed(base_url, db_path, page), cadence="quarterly")
    row = today.upcoming_recurring(db_probe.rule_id(db_path, "edit-rule"))
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    _override_from_today(page, row)
    dialog = edit_dialogs.occurrence_dialog("Groceries")
    expect(to_playwright(page, dialog)).to_be_visible()
    # A month with no quarterly occurrence.
    to_playwright(page, edit_dialogs.month_next(dialog)).click()
    _save_override(page, dialog, "77.00")
    expect(to_playwright(page, edit_dialogs.summary.inside(dialog))).to_contain_text(
        "no occurrence"
    )
    expect(to_playwright(page, dialog)).to_be_visible()
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM recurring_rule_overrides") == 0
