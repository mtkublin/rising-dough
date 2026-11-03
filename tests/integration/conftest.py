"""Shared fixtures for integration tests.

Provides a per-test temp SQLite file, migrated + seeded, and standard
builders mirroring the T-040 fixtures. Mocks the FX HTTP boundary via a
``httpx.MockTransport`` factory.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import AmountFormula, NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    fx as fx_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as txn_repo,
)

USER_ID = 1


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "integration.sqlite"


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}")


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    c = get_connection(settings)
    apply_migrations(c)
    try:
        yield c
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


@pytest.fixture
def make_account(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        name: str = "Checking",
        currency: str = "PLN",
        opening_balance: int = 0,
    ) -> int:
        return accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(name=name, currency=currency, opening_balance=opening_balance),
        ).id

    return _make


@pytest.fixture
def make_category(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        name: str = "Groceries",
        direction: Direction = Direction.EXPENSE,
    ) -> int:
        return categories_repo.create(conn, USER_ID, NewCategory(name=name, direction=direction)).id

    return _make


@pytest.fixture
def make_transaction(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        account_id: int,
        category_id: int,
        amount: int = 1000,
        operation_date: date = date(2026, 1, 1),
        description: str = "",
        dest_account_id: int | None = None,
        promoted_from_planned_id: int | None = None,
    ) -> int:
        return txn_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=operation_date,
                category_id=category_id,
                account_id=account_id,
                dest_account_id=dest_account_id,
                amount=amount,
                description=description,
                promoted_from_planned_id=promoted_from_planned_id,
            ),
        ).id

    return _make


@pytest.fixture
def make_planned(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        account_id: int,
        category_id: int,
        amount: int = 1000,
        operation_date: date = date(2026, 1, 15),
        recurring_rule_id: int | None = None,
        occurrence_date: date | None = None,
    ) -> int:
        return planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=operation_date,
                category_id=category_id,
                account_id=account_id,
                amount=amount,
                recurring_rule_id=recurring_rule_id,
                occurrence_date=occurrence_date,
            ),
        ).id

    return _make


@pytest.fixture
def make_rule(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        account_id: int,
        category_id: int,
        cadence: Cadence = Cadence.MONTHLY,
        start_date: date = date(2026, 1, 15),
        amount: int = 1000,
        description: str = "",
        amount_formula: AmountFormula | None = None,
    ) -> int:
        return recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=cadence,
                start_date=start_date,
                category_id=category_id,
                account_id=account_id,
                default_amount=amount,
                default_description=description,
                amount_formula=amount_formula,
            ),
        ).id

    return _make


@pytest.fixture
def make_fx_rate(conn: sqlite3.Connection) -> Callable[..., None]:
    def _make(
        *,
        on_date: date,
        from_ccy: str = "EUR",
        to_ccy: str = "PLN",
        rate: str = "4.30",
    ) -> None:
        fx_repo.upsert_rate(
            conn,
            NewFxRate(
                date=on_date,
                from_ccy=from_ccy,
                to_ccy=to_ccy,
                rate=Decimal(rate),
            ),
        )

    return _make


# ---------------------------------------------------------------------------
# FX HTTP mocking helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def frankfurter_mock_factory() -> Callable[[dict[str, Any]], httpx.Client]:
    """Return a factory that builds an httpx.Client with a pre-canned response map.

    Keys of ``routes`` are URL paths (e.g. ``/2026-02-01``) → response payload dict.
    Any un-mocked URL raises AssertionError so tests fail loud on surprise calls.
    """

    def _factory(routes: dict[str, Any]) -> httpx.Client:
        def _handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            payload = routes.get(path)
            if payload is None:
                raise AssertionError(
                    f"Unexpected fx HTTP call to {path} (expected one of {list(routes)!r})"
                )
            return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

        transport = httpx.MockTransport(_handler)
        return httpx.Client(transport=transport, base_url="https://api.frankfurter.app")

    return _factory


@pytest.fixture
def frankfurter_error_client() -> httpx.Client:
    """An httpx.Client that always errors on connect (fallback path)."""

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    return httpx.Client(
        transport=httpx.MockTransport(_handler),
        base_url="https://api.frankfurter.app",
    )
