"""T-069 FAB removed per manual-audit remediation #31.

Mockups carry no floating action button on any surface; the top-bar
``+ Add`` pill + the ``n`` keyboard shortcut are the only new-entry
affordances. These assertions guard against regression — if any route
re-introduces a FAB, these tests fail.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from tests.ui_map import _html, entries

HX = {"HX-Request": "true"}


def _assert_no_fab(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    fab = soup.find("button", class_="fab")
    assert fab is None, f"FAB should not render on {path}"


def test_no_fab_on_any_route(client: TestClient) -> None:
    for path in (
        "/",
        "/ledger",
        "/ledger?view=planned",
        "/ledger?view=recurring",
        "/accounts",
        "/budget",
        "/settings",
        "/forecast",
        "/today",
        "/plan",
    ):
        _assert_no_fab(client, path)


def _dialog_form(html: str) -> Tag:
    """The form of the single new-entry dialog in a fragment (T-UR07b)."""
    form = _html.resolve_one(html, entries.dialog).find("form")
    assert isinstance(form, Tag)
    return form


def test_new_transaction_opens_the_dialog_on_happened(client: TestClient) -> None:
    response = client.get("/transactions/new", headers=HX)
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#modal-root"
    assert _dialog_form(response.text).get("hx-post") == "/transactions"
    assert _html.resolve_one(response.text, entries.tab_happened).get("aria-current") == "page"


def test_new_planned_opens_the_dialog_on_planned(client: TestClient) -> None:
    response = client.get("/planned/new", headers=HX)
    assert response.status_code == 200
    assert _dialog_form(response.text).get("hx-post") == "/planned"
    assert _html.resolve_one(response.text, entries.tab_planned).get("aria-current") == "page"


def test_new_recurring_opens_the_dialog_on_repeats(client: TestClient) -> None:
    response = client.get("/recurring/new", headers=HX)
    assert response.status_code == 200
    assert _dialog_form(response.text).get("hx-post") == "/recurring"
    assert _html.resolve_one(response.text, entries.tab_repeats).get("aria-current") == "page"
