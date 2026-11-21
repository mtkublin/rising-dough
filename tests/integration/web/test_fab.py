"""T-069 FAB removed per manual-audit remediation #31.

Mockups carry no floating action button on any surface; the top-bar
``+ Add`` pill + the ``n`` keyboard shortcut are the only new-entry
affordances. These assertions guard against regression — if any route
re-introduces a FAB, these tests fail.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient


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
    response = client.get("/transactions/new")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.find("div", attrs={"data-slideover": True})
    assert isinstance(container, Tag)
    assert container.get("role") == "dialog"
    assert container.get("aria-modal") == "true"
    assert 'hx-post="/transactions"' in response.text


def test_new_planned_returns_slideover(client: TestClient) -> None:
    response = client.get("/planned/new")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.find("div", attrs={"data-slideover": True})
    assert isinstance(container, Tag)
    assert 'hx-post="/planned"' in response.text


def test_new_recurring_returns_slideover(client: TestClient) -> None:
    response = client.get("/recurring/new")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.find("div", attrs={"data-slideover": True})
    assert isinstance(container, Tag)
    assert 'hx-post="/recurring"' in response.text
