"""T-069 FAB removed per manual-audit remediation #31.

Mockups carry no floating action button on any surface; the top-bar
``+ Add`` pill + the ``n`` keyboard shortcut are the only new-entry
affordances. These assertions guard against regression — if any route
re-introduces a FAB, these tests fail.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from tests.ui_map import _html, shell

HX = {"HX-Request": "true"}


def _slideover(html: str) -> Tag:
    """The single slide-over dialog in a fragment (the shell's own dialogs excluded)."""
    found = [d for d in _html.resolve(html, shell.dialog) if d.has_attr("data-slideover")]
    assert len(found) == 1
    return found[0]


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


def test_new_transaction_returns_slideover(client: TestClient) -> None:
    response = client.get("/transactions/new", headers=HX)
    assert response.status_code == 200
    container = _slideover(response.text)
    assert container.get("role") == "dialog"
    assert container.get("aria-modal") == "true"
    form = _slideover(response.text).find("form")
    assert isinstance(form, Tag)
    assert form.get("hx-post") == "/transactions"


def test_new_planned_returns_slideover(client: TestClient) -> None:
    response = client.get("/planned/new", headers=HX)
    assert response.status_code == 200
    form = _slideover(response.text).find("form")
    assert isinstance(form, Tag)
    assert form.get("hx-post") == "/planned"


def test_new_recurring_returns_slideover(client: TestClient) -> None:
    response = client.get("/recurring/new", headers=HX)
    assert response.status_code == 200
    form = _slideover(response.text).find("form")
    assert isinstance(form, Tag)
    assert form.get("hx-post") == "/recurring"
