"""T-070 — Legacy URL redirect map.

ADR-0023 collapses the Phase 3 nine-tab IA into four nav items plus a
Settings drawer. For one release the Phase 3 page URLs stay live and
return ``302`` to their new home so bookmarks keep working. This module
pins every redirect in the map, and additionally confirms that

- the HTMX fragment aliases (``/transactions/table``, ``/planned/table``)
  continue to return 200 with the ledger fragment shape, and
- the Phase 3 CRUD sub-routes (``/transactions/new``, ``/planned/new``,
  ``/recurring/new``, ``/categories/new`` and matching ``POST``s) are
  **not** redirected because the FAB (T-069), palette (T-068) and
  Settings drawer (T-067) reuse them.

The redirects are intentionally ``302`` for one release; a follow-up
task flips them to ``301`` once the new IA is stable.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
)

USER_ID = 1

# ``old → new`` tuples. Kept here so the acceptance list in
# ADR-0023 maps 1:1 to a parametrised test case.
_REDIRECTS: tuple[tuple[str, str], ...] = (
    ("/transactions", "/ledger?view=actual"),
    ("/planned", "/ledger?view=planned"),
    ("/recurring", "/ledger?view=recurring"),
    ("/categories", "/settings?tab=categories"),
    ("/analytics", "/budget#budget-breakdown"),
    ("/budget/manage", "/budget#budget-rules"),
)


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    """Enough data so every landing page can render once redirected."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        groc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        return {"acc": acc.id, "groc": groc.id}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Page-level 302 redirects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("old", "new"), _REDIRECTS)
def test_legacy_page_redirects(client: TestClient, old: str, new: str) -> None:
    """Every legacy page URL returns 302 with the mapped Location."""
    r = client.get(old, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == new


def test_legacy_transactions_redirects(client: TestClient) -> None:
    r = client.get("/transactions", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=actual"


def test_legacy_planned_redirects(client: TestClient) -> None:
    r = client.get("/planned", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=planned"


def test_legacy_recurring_redirects(client: TestClient) -> None:
    r = client.get("/recurring", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=recurring"


def test_legacy_categories_redirects(client: TestClient) -> None:
    r = client.get("/categories", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/settings?tab=categories"


def test_legacy_analytics_redirects(client: TestClient) -> None:
    r = client.get("/analytics", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/budget#budget-breakdown"


def test_legacy_budget_manage_redirects(client: TestClient) -> None:
    r = client.get("/budget/manage", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/budget#budget-rules"


# ---------------------------------------------------------------------------
# CRUD sub-routes stay live
# ---------------------------------------------------------------------------


def test_crud_subroutes_get_new_still_200(client: TestClient, seeded: dict[str, int]) -> None:
    """GET on the ``/new`` sub-routes must not redirect — the FAB uses them."""
    for path in ("/transactions/new", "/planned/new", "/recurring/new", "/categories/new"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200, f"{path} returned {r.status_code}"


def test_crud_subroutes_post_create_still_200(client: TestClient, seeded: dict[str, int]) -> None:
    """POST on each create sub-route still persists an entity and returns 200."""
    today = date(2026, 10, 20).isoformat()
    posts = (
        (
            "/transactions",
            {
                "operation_date": today,
                "category_id": str(seeded["groc"]),
                "account_id": str(seeded["acc"]),
                "amount": "10.00",
                "description": "redirect-test",
            },
        ),
        (
            "/planned",
            {
                "operation_date": today,
                "category_id": str(seeded["groc"]),
                "account_id": str(seeded["acc"]),
                "amount": "5.00",
                "description": "redirect-test-planned",
            },
        ),
        (
            "/recurring",
            {
                "cadence": "monthly",
                "start_date": today,
                "category_id": str(seeded["groc"]),
                "account_id": str(seeded["acc"]),
                "default_amount": "7.00",
            },
        ),
        ("/categories", {"name": "Redirect-Test-Cat", "direction": "expense"}),
    )
    for path, data in posts:
        r = client.post(path, data=data, follow_redirects=False)
        assert r.status_code == 200, f"POST {path} returned {r.status_code}: {r.text[:200]}"


# ---------------------------------------------------------------------------
# HTMX fragment aliases
# ---------------------------------------------------------------------------


def test_htmx_fragment_aliases_still_live(client: TestClient, seeded: dict[str, int]) -> None:
    """``/transactions/table`` and ``/planned/table`` must stay 200 fragments."""
    for path, token in (
        ("/transactions/table", "txn-table"),
        ("/planned/table", "planned-table"),
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert "<html" not in r.text, f"{path} returned a full page, not a fragment"
        assert token in r.text, f"{path} missing ledger fragment anchor {token!r}"
