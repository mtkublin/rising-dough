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
    ("cat", "typed", "booked"),
    [("expense", "1500", 50_000), ("income", "500", -50_000)],
)
def test_posted_category_is_ignored_and_books_to_reconciliation(
    client: TestClient,
    world: dict[str, int],
    _migrated: Settings,
    cat: str,
    typed: str,
    booked: int,
) -> None:
    # D8R (ADR-0011 amendment 2026-11-26): a posted category_id, matching or
    # not, is ignored; the adjustment always books to Reconciliation.
    r = client.post(
        f"/accounts/{world['a']}/reconcile",
        data={"actual_balance": typed, "category_id": str(world[cat])},
    )
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        rows = conn.execute(
            "SELECT c.name, t.amount FROM transactions t JOIN categories c ON c.id = t.category_id"
        ).fetchall()
        audits = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'transaction' "
            "AND operation = 'create'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert [tuple(x) for x in rows] == [("Reconciliation", booked)]
    assert audits == 1
    assert _state(_migrated, world["a"]) == (1, OPENING + booked)
