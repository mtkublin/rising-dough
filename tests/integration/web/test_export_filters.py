"""T-UR34b (ADR-0134 section 6): exports honour the live tab filters."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from tests.auth_support import seed_login_user

pytestmark = pytest.mark.integration

USER_ID = 1
OTHER_ID = 2
# The Planned export window is [today-30d, today+180d] on the frozen app clock (ADR-0140),
# so every date is derived from it; nothing here depends on the wall or the shifted clock.
INSIDE_DAYS = 10
OUTSIDE_DAYS = 300


def _on(settings: Settings, days: int) -> date:
    return clock.today_local(settings) + timedelta(days=days)


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    main = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    sav = accounts_repo.create(db, USER_ID, NewAccount(name="Savings", currency="PLN"))
    rent = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    food = categories_repo.create(
        db, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    )
    pay = categories_repo.create(db, USER_ID, NewCategory(name="Pay", direction=Direction.INCOME))
    return {"main": main.id, "sav": sav.id, "rent": rent.id, "food": food.id, "pay": pay.id}


def _txn(
    db: sqlite3.Connection, acc: int, cat: int, amount: int, desc: str, *, user: int = 1
) -> None:
    transactions_repo.create(
        db,
        user,
        NewTransaction(
            operation_date=date(2026, 10, 5),
            category_id=cat,
            account_id=acc,
            amount=amount,
            description=desc,
        ),
    )


def _planned(
    db: sqlite3.Connection, acc: int, cat: int, amount: int, desc: str, *, day: date
) -> None:
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=day, category_id=cat, account_id=acc, amount=amount, description=desc
        ),
    )


def _rows(text: str) -> list[str]:
    return text.strip().splitlines()[1:]


def test_transactions_export_honours_direction(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _txn(db, ids["main"], ids["food"], 1250, "lunch")
    _txn(db, ids["main"], ids["pay"], 500000, "salary")
    r = client.get("/transactions/export?format=csv&direction=expense")
    assert r.status_code == 200
    assert [ln.split(",")[2:5] for ln in _rows(r.text)] == [["1250", "PLN", "lunch"]]
    r = client.get("/transactions/export?format=csv&direction=income")
    assert [ln.split(",")[2:5] for ln in _rows(r.text)] == [["500000", "PLN", "salary"]]
    assert len(_rows(client.get("/transactions/export?format=csv").text)) == 2


def test_transactions_export_hides_other_users_rows(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _txn(db, ids["main"], ids["food"], 1250, "mine")
    seed_login_user(db, user_id=OTHER_ID, email="two@example.test")
    acc = accounts_repo.create(db, OTHER_ID, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(
        db, OTHER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    )
    _txn(db, acc.id, cat.id, 999, "theirs", user=OTHER_ID)
    r = client.get("/transactions/export?format=csv&direction=expense")
    assert [ln.split(",")[4] for ln in _rows(r.text)] == ["mine"]


def test_planned_export_maps_account_category_search(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int], _migrated: Settings
) -> None:
    inside = _on(_migrated, INSIDE_DAYS)
    outside = _on(_migrated, OUTSIDE_DAYS)
    _planned(db, ids["main"], ids["rent"], 200000, "Rent October", day=inside)
    _planned(db, ids["main"], ids["rent"], 300000, "Garage", day=inside)
    _planned(db, ids["sav"], ids["rent"], 400000, "Rent savings", day=inside)
    _planned(db, ids["main"], ids["food"], 5000, "Rent food", day=inside)
    _planned(db, ids["main"], ids["pay"], 700000, "Rent income", day=inside)
    _planned(db, ids["main"], ids["rent"], 600000, "Rent far away", day=outside)
    seed_login_user(db, user_id=OTHER_ID, email="two@example.test")
    acc = accounts_repo.create(db, OTHER_ID, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(
        db, OTHER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    planned_repo.create(
        db,
        OTHER_ID,
        NewPlannedTransaction(
            operation_date=inside,
            category_id=cat.id,
            account_id=acc.id,
            amount=1,
            description="Rent x",
        ),
    )
    q = f"account_id={ids['main']}&category_id={ids['rent']}&q=rent"
    r = client.get(f"/planned/export?format=csv&{q}")
    assert r.status_code == 200
    assert [ln.split(",")[1:4] for ln in _rows(r.text)] == [
        [inside.isoformat(), "200000", "Rent October"]
    ]
    r = client.get("/planned/export?format=csv&direction=income")
    assert [ln.split(",")[2:4] for ln in _rows(r.text)] == [["700000", "Rent income"]]
    # default window is the Ledger planned window, so the far row is out unless asked for
    assert _rows(client.get("/planned/export?format=csv&q=far").text) == []
    span = f"date_from={outside - timedelta(days=30)}&date_to={outside + timedelta(days=30)}"
    r = client.get(f"/planned/export?format=csv&q=far&{span}")
    assert [ln.split(",")[2:4] for ln in _rows(r.text)] == [["600000", "Rent far away"]]
