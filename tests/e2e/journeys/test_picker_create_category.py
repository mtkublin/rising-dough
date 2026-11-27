"""Journey: a category created from the new-entry picker is selected in place (T-UR68).

The dialog stays open with its typed amount and note; saving stores the entry on the new category.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.e2e.ui_actions import choose_account, fill_stable, open_new_entry, save_entry
from tests.ui_map import entries
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def _is_hero_refresh(response: Any) -> bool:
    return "hero=1" in response.url


def _open_search_with(world: World, text: str) -> None:
    to_playwright(world.page, entries.category_search).click()
    to_playwright(world.page, entries.category_query).fill(text)


def test_new_category_from_the_picker_is_selected_and_the_entry_saves_on_it(world: World) -> None:
    account = world.account("Checking")
    world.goto("/today")
    open_new_entry(world.page)
    choose_account(world.page, "Checking")
    fill_stable(world.find(entries.hero_amount), "7.00")
    fill_stable(world.find(entries.field_note.inside(entries.dialog)), "picker-created")

    _open_search_with(world, "Zzz Test")
    with world.page.expect_response(_is_hero_refresh):  # the hero follows the new category
        world.find(entries.category_create("Zzz Test")).click()

    expect(world.find(entries.dialog)).to_be_visible()
    expect(world.find(entries.category_search)).to_contain_text("Zzz Test")
    expect(world.find(entries.hero_amount)).to_have_value("7.00")
    expect(world.find(entries.field_note.inside(entries.dialog))).to_have_value("picker-created")
    created = world.rows("SELECT * FROM categories WHERE name = 'Zzz Test'")
    assert len(created) == 1
    assert created[0]["direction"] == "expense"
    assert world.audit_ops("category", created[0]["id"]) == ["create"]

    save_entry(world.page)
    txn = world.wait_rows("SELECT * FROM transactions WHERE description = 'picker-created'")
    assert len(txn) == 1
    assert (txn[0]["amount"], txn[0]["account_id"], txn[0]["category_id"]) == (
        700,
        account,
        created[0]["id"],
    )


def test_a_duplicate_name_shows_the_error_in_the_picker_and_keeps_the_dialog(
    world: World,
) -> None:
    """The system Reconciliation category is not offered, so typing its name reaches no-match."""
    world.account("Checking")
    world.goto("/today")
    open_new_entry(world.page)
    fill_stable(world.find(entries.field_note.inside(entries.dialog)), "keep-me")
    _open_search_with(world, "reconciliation")
    world.find(entries.category_create("reconciliation")).click()

    expect(world.find(entries.category_create_error)).to_have_text(
        "▲ A category with this name already exists"
    )
    expect(world.find(entries.dialog)).to_be_visible()
    expect(world.find(entries.field_note.inside(entries.dialog))).to_have_value("keep-me")
    assert world.scalar("SELECT count(*) FROM categories WHERE lower(name) = 'reconciliation'") == 1
