"""T-070 — Legacy URL redirect map.

ADR-0023 collapses the Phase 3 nine-tab IA into four nav items plus a
Settings drawer. For one release the Phase 3 page URLs stay live and
return ``302`` to their new home so bookmarks keep working. This module
pins every redirect in the map, and additionally confirms that

- the HTMX fragment aliases (``/transactions/table``, ``/planned/table``)
  continue to return 200 with the ledger fragment shape, and
- the Phase 3 CRUD sub-routes (``/categories/new`` and the matching ``POST``s) are
  **not** redirected because the Settings drawer (T-067) reuses them; the new-entry
  dialog is ``/add`` (T-UR15b removed the ``/{transactions,planned,recurring}/new`` GETs).

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
from tests.ui_map import _html, shell
from tests.ui_map.locator import by_id

USER_ID = 1

# ``old → new`` tuples. Kept here so the acceptance list in
# ADR-0023 maps 1:1 to a parametrised test case.
_REDIRECTS: tuple[tuple[str, str], ...] = (("/transactions", "/ledger?view=actual"),)


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


# ---------------------------------------------------------------------------
# CRUD sub-routes stay live
# ---------------------------------------------------------------------------


def test_crud_subroutes_get_new_still_200(client: TestClient, seeded: dict[str, int]) -> None:
    """GET on the ``/new`` sub-route must not redirect — the Settings drawer uses it."""
    for path in ("/categories/new",):
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
    )
    for path, data in posts:
        r = client.post(path, data=data, follow_redirects=False)
        assert r.status_code == 200, f"POST {path} returned {r.status_code}: {r.text[:200]}"


# ---------------------------------------------------------------------------
# HTMX fragment aliases
# ---------------------------------------------------------------------------


def test_htmx_fragment_aliases_still_live(client: TestClient, seeded: dict[str, int]) -> None:
    """``/transactions/table`` and ``/planned/table`` must stay 200 fragments."""
    for path, anchor in (
        ("/transactions/table", by_id("txn-table")),
        ("/planned/table", by_id("planned-table")),
    ):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert not _html.exists(r.text, shell.main), f"{path} returned a full page, not a fragment"
        assert _html.exists(r.text, anchor), (
            f"{path} missing ledger fragment anchor {anchor.value!r}"
        )
