"""Small UI-map-driven actions shared by the e2e journeys (ADR-0106 section 2)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.ui_map import entries, ledger, rd_shell, shell
from tests.ui_map.locator import Locator, to_playwright


def pick(page: Any, field: Locator, option: str, *, scope: Locator = shell.slideover) -> None:
    """Choose ``option`` in the combobox behind the labelled ``field`` (inside ``scope``)."""
    to_playwright(page, field.inside(scope)).click()
    to_playwright(page, ledger.combobox_option(option).inside(scope)).click()


def open_add_slide_over(page: Any) -> None:
    """Open the New entry slide-over from the top bar and wait for it."""
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, shell.add_button).first.click()
    expect(to_playwright(page, shell.slideover)).to_be_visible()


def open_new_entry(page: Any) -> None:
    """Open the new-entry dialog from the new shell's top bar and wait for it."""
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, rd_shell.new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()


def choose_category(page: Any, name: str) -> None:
    """Pick ``name`` in the new-entry dialog's category search (recent radios are not needed)."""
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill(name)
    with page.expect_response(_is_hero_refresh):  # the hero follows the category (sign)
        query.press("Enter")
    _settle(page)


def choose_account(page: Any, name: str) -> None:
    field = to_playwright(page, entries.field_account)
    if field.evaluate("el => el.selectedOptions[0].label") == name:
        return  # no change event, no refresh
    with page.expect_response(_is_hero_refresh):  # the hero follows the account (currency)
        field.select_option(label=name)
    _settle(page)


def _is_hero_refresh(response: Any) -> bool:
    return "hero=1" in response.url


def _settle(page: Any) -> None:
    """Let the hero swap land before the amount is typed (it re-renders the amount input)."""
    page.wait_for_timeout(300)
