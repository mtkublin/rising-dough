"""New-entry hero refresh vs typing (T-UR04g): an amount typed during GET /add?hero=1 survives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import (
    choose_account,
    choose_category,
    fill_stable,
    open_new_entry,
    quiesce,
    save_entry,
)
from tests.ui_map import entries
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_HERO_URL = "**/add?*hero=1*"


def _seed(base_url: str, page: Page) -> None:
    forms: list[tuple[str, dict[str, str | float | bool]]] = [
        ("/accounts", {"name": "Checking", "currency": "PLN", "opening_balance": "500.00"}),
        ("/accounts", {"name": "Yen", "currency": "JPY", "opening_balance": "1000"}),
        ("/categories", {"name": "Groceries", "direction": "expense"}),
        ("/categories", {"name": "Salary", "direction": "income"}),
    ]
    for path, form in forms:
        assert page.request.post(f"{base_url}{path}", form=form).ok


def test_amount_typed_during_the_hero_refresh_is_kept_and_stored(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held: list[Any] = []

    def hold(route: Any) -> None:
        held.append(route)

    # Hold the refresh so the amount is typed while it is in flight.
    page.route(_HERO_URL, hold)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    for _ in range(40):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the account change must request a hero refresh"
    amount = to_playwright(page, entries.hero_amount)
    amount.fill("1234")
    held[0].continue_()
    expect(to_playwright(page, entries.dialog)).to_contain_text("JPY")
    expect(amount).to_have_value("1234")
    expect(amount).to_have_attribute("placeholder", "0")
    fill_stable(to_playwright(page, entries.field_note), "race-added")
    save_entry(page)
    expect(to_playwright(page, entries.dialog)).not_to_be_visible()
    assert db_probe.txn_amounts(db_path, "race-added") == [1234]


def test_note_typed_during_the_hero_refresh_is_kept_and_posted(
    live_server: tuple[str, Path], page: Page
) -> None:
    """QFIX10: a refresh answered after the note was typed never replaces the note."""
    base_url, db_path = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    to_playwright(page, entries.tab_planned).click()
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    to_playwright(page, entries.hero_amount).fill("25")
    note = to_playwright(page, entries.field_note)
    note.fill("typed-in-flight")
    held[0].continue_()
    expect(to_playwright(page, entries.dialog)).to_contain_text("JPY")
    expect(note).to_have_value("typed-in-flight")
    posted = save_entry(page, "planned")
    assert "description=typed-in-flight" in posted, posted
    stored = db_probe.rows(db_path, "SELECT description FROM planned_transactions")
    assert [row[0] for row in stored] == ["typed-in-flight"]


def _selected_account(page: Page) -> str:
    field = to_playwright(page, entries.field_account.inside(entries.dialog))
    return str(field.evaluate("el => el.selectedOptions[0].label"))


def _assert_carried(page: Page, amount_name: str) -> None:
    amount = to_playwright(page, entries.hero_amount)
    expect(amount).to_have_value("35.50")
    expect(amount).to_have_attribute("name", amount_name)
    expect(to_playwright(page, entries.category_group)).to_contain_text("Takeaway")
    assert _selected_account(page) == "Credit Card"
    expect(to_playwright(page, entries.field_note)).to_have_value("lunch")


def test_tab_switch_carries_amount_category_account_and_note(
    live_server: tuple[str, Path], page: Page
) -> None:
    """T-UR44 (D5-b): happened -> planned -> repeats -> happened keeps what was typed."""
    base_url, _ = live_server
    _seed(base_url, page)
    extra: dict[str, str | float | bool] = {
        "name": "Credit Card",
        "currency": "PLN",
        "opening_balance": "0.00",
    }
    assert page.request.post(f"{base_url}/accounts", form=extra).ok
    takeaway: dict[str, str | float | bool] = {"name": "Takeaway", "direction": "expense"}
    assert page.request.post(f"{base_url}/categories", form=takeaway).ok
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Takeaway")
    choose_account(page, "Credit Card")
    fill_stable(to_playwright(page, entries.hero_amount), "35.50")
    fill_stable(to_playwright(page, entries.field_note), "lunch")
    for link, amount_name in (
        (entries.tab_planned, "amount"),
        (entries.tab_repeats, "default_amount"),
        (entries.tab_happened, "amount"),
    ):
        quiesce(page)
        to_playwright(page, link).click()
        expect(to_playwright(page, link)).to_have_attribute("aria-current", "page")
        quiesce(page)
        _assert_carried(page, amount_name)


def test_failed_hero_refresh_marks_the_unit_stale(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    page.route(_HERO_URL, lambda route: route.fulfill(status=500, body="boom"))
    to_playwright(page, entries.field_account).select_option(label="Yen")
    expect(to_playwright(page, entries.dialog)).to_contain_text("\N{EM DASH}")


def _hold_hero(page: Page) -> list[Any]:
    held: list[Any] = []

    def hold(route: Any) -> None:
        held.append(route)

    page.route(_HERO_URL, hold)
    return held


def _wait_for(page: Page, held: list[Any], count: int) -> None:
    for _ in range(60):
        if len(held) >= count:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"expected {count} hero request(s), saw {len(held)}")


def test_newer_hero_refresh_supersedes_the_older_one(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    # A second change while the first refresh is in flight: category Salary (income, sign +).
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill("Salary")
    query.press("Enter")
    # Queue last: the first refresh completes, then only the latest one runs. Nothing is aborted.
    held[0].continue_()
    _wait_for(page, held, 2)
    held[1].continue_()
    dialog = to_playwright(page, entries.dialog)
    expect(dialog).to_contain_text("JPY")
    expect(dialog).to_contain_text("+")
    expect(dialog).not_to_contain_text("\N{MINUS SIGN}")


def test_save_wins_over_a_hero_refresh_in_flight(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Checking")
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    to_playwright(page, entries.hero_amount).fill("777")
    to_playwright(page, entries.field_note).fill("save-wins")
    save_entry(page)
    expect(to_playwright(page, entries.dialog)).not_to_be_visible()
    assert db_probe.txn_amounts(db_path, "save-wins") == [777]


def test_picking_a_category_with_search_and_enter_requests_one_hero_refresh(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    seen: list[str] = []
    problems: list[str] = []
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    page.on("requestfailed", lambda req: problems.append(req.url))
    page.on("request", lambda req: seen.append(req.url) if "hero=1" in req.url else None)
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill("Salary")
    query.press("Enter")
    expect(to_playwright(page, entries.dialog)).to_contain_text("+")
    page.wait_for_timeout(600)  # a second (blur) change would have requested by now
    assert len(seen) == 1, seen
    assert problems == []  # no aborted request, no htmx:sendAbort console error


def test_caret_stays_after_the_restored_amount_so_typing_continues(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    amount = to_playwright(page, entries.hero_amount)
    amount.click()
    page.wait_for_timeout(200)  # the focus-select frame passes before the user types
    amount.press_sequentially("1234")
    held[0].continue_()
    expect(to_playwright(page, entries.dialog)).to_contain_text("JPY")
    expect(amount).to_have_value("1234")
    page.wait_for_timeout(600)  # htmx settles and the focus-select frame passes
    amount.press_sequentially("5")  # a selected amount would be replaced by this key
    expect(amount).to_have_value("12345")
