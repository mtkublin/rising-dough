"""T-Q217 (Q-005, ADR-0008 amendment 2026-11-21): reconcile category vs delta sign."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts as accounts_repo, categories as categories_repo
from budget_planner.services import balance as balance_svc
from tests.ui_map import _html, errors

USER_ID = 1
OPENING = 100_000


@pytest.fixture
def world(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="A", currency="PLN", opening_balance=OPENING)
        )
        ex = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        inc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Pay", direction=Direction.INCOME)
        )
        return {"a": acc.id, "expense": ex.id, "income": inc.id}
    finally:
        conn.close()


def _state(settings: Settings, account_id: int) -> tuple[int, int]:
    conn = get_connection(settings)
    try:
        rows = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
        return rows, balance_svc.derive_balance(conn, USER_ID, account_id)
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("cat", "typed"),
    [("expense", "1500"), ("income", "500")],
)
def test_mismatching_category_is_rejected_and_writes_nothing(
    client: TestClient, world: dict[str, int], _migrated: Settings, cat: str, typed: str
) -> None:
    r = client.post(
        f"/accounts/{world['a']}/reconcile",
        data={"actual_balance": typed, "category_id": str(world[cat])},
    )
    assert r.status_code == 422
    assert f"a {cat} category cannot book" in _html.all_text(r.text, errors.alert)
    assert _state(_migrated, world["a"]) == (0, OPENING)


@pytest.mark.parametrize(
    ("cat", "typed", "minor"),
    [("income", "1500", 150_000), ("expense", "500", 50_000)],
)
def test_matching_category_lands_on_typed_balance(
    client: TestClient, world: dict[str, int], _migrated: Settings, cat: str, typed: str, minor: int
) -> None:
    r = client.post(
        f"/accounts/{world['a']}/reconcile",
        data={"actual_balance": typed, "category_id": str(world[cat])},
    )
    assert r.status_code == 200
    assert _state(_migrated, world["a"]) == (1, minor)
