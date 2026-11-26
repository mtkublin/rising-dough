"""Tab switch of the new-entry dialog carries the typed values (T-UR44, operator D5-b)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from bs4 import Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts as accounts_repo, categories as categories_repo
from tests.ui_map import _html, entries
from tests.ui_map.locator import Locator

USER_ID = 1
_HX = {"HX-Request": "true"}


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    accounts_repo.create(db, USER_ID, NewAccount(name="Cash", currency="PLN"))
    card = accounts_repo.create(db, USER_ID, NewAccount(name="Credit Card", currency="PLN"))
    food = categories_repo.create(
        db, USER_ID, NewCategory(name="Takeaway", direction=Direction.EXPENSE)
    )
    return {"account": card.id, "category": food.id}


def _note(html: str, locator: Locator) -> str:
    node = _html.resolve_one(html, locator)
    return node.get_text() if node.name == "textarea" else str(node.get("value"))


def test_tab_links_send_the_form_values_without_the_csrf_token(client: TestClient) -> None:
    r = client.get("/add?when=happened&dialog=1", headers=_HX)
    for tab in (entries.tab_happened, entries.tab_planned, entries.tab_repeats):
        link = _html.resolve_one(r.text, tab)
        assert link.get("hx-include") == "closest form"
        assert link.get("hx-params") == "not _csrf_token"


def test_planned_tab_opens_with_the_typed_values(client: TestClient, ids: dict[str, int]) -> None:
    query = (
        f"/add?when=planned&dialog=1&amount=35.50&category_id={ids['category']}"
        f"&account_id={ids['account']}&description=lunch"
    )
    r = client.get(query, headers=_HX)
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "35.50"
    account = _html.resolve_one(r.text, entries.field_account)
    selected = account.find("option", selected=True)
    assert isinstance(selected, Tag)
    assert selected.get("value") == str(ids["account"])
    assert _note(r.text, entries.field_note) == "lunch"
    assert _html.resolve_one(r.text, entries.tab_planned).get("aria-current") == "page"


def test_repeats_tab_maps_amount_and_note_names_in_both_directions(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get(
        f"/add?when=repeats&dialog=1&amount=35.50&description=lunch&account_id={ids['account']}",
        headers=_HX,
    )
    hero = _html.resolve_one(r.text, entries.hero_amount)
    assert (hero.get("name"), hero.get("value")) == ("default_amount", "35.50")
    assert _note(r.text, entries.field_note) == "lunch"
    back = client.get(
        "/add?when=happened&dialog=1&default_amount=12.00&default_description=rent",
        headers=_HX,
    )
    hero = _html.resolve_one(back.text, entries.hero_amount)
    assert (hero.get("name"), hero.get("value")) == ("amount", "12.00")
    assert _note(back.text, entries.field_note) == "rent"


def test_a_tab_only_field_is_not_echoed_on_the_other_tab(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get("/add?when=happened&dialog=1&due_date=2031-02-03&amount=5", headers=_HX)
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "5.00"
    assert "2031-02-03" not in r.text
