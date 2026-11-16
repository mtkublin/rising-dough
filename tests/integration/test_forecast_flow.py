"""Forecast determinism + FX conversion flow (ADR-0015, ADR-0006).

The service is pure w.r.t. the DB snapshot + FX cache + injected
``today``. Same inputs → same outputs. Editing a planned row changes
the forecast.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from budget_planner.domain.enums import Cadence
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import PatchPlannedTransaction
from budget_planner.repositories import fx as fx_repo, planned as planned_repo
from budget_planner.services import forecast as forecast_service

USER_ID = 1

pytestmark = pytest.mark.integration


def _offline_client() -> httpx.Client:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    return httpx.Client(transport=httpx.MockTransport(_handler))


def test_forecast_is_deterministic_same_inputs_same_output(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_transaction: Callable[..., int],
    make_rule: Callable[..., int],
) -> None:
    account_id = make_account(name="Checking", opening_balance=100000)
    category_id = make_category(name="Food")
    make_transaction(
        account_id=account_id,
        category_id=category_id,
        amount=5000,
        operation_date=date(2026, 1, 10),
    )
    make_rule(
        account_id=account_id,
        category_id=category_id,
        cadence=Cadence.MONTHLY,
        start_date=date(2026, 1, 15),
        amount=10000,
    )

    client = _offline_client()
    first = forecast_service.forecast(
        conn, USER_ID, client, today=date(2026, 1, 1), horizon_days=30, base_currency="PLN"
    )
    second = forecast_service.forecast(
        conn, USER_ID, client, today=date(2026, 1, 1), horizon_days=30, base_currency="PLN"
    )
    assert first == second


def test_forecast_converts_cross_currency_to_base(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
) -> None:
    # EUR account with opening 10000 (= 100.00 EUR).
    make_account(name="EUR account", currency="EUR", opening_balance=10000)

    fx_repo.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 1, 1),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.30"),
        ),
    )
    series = forecast_service.forecast(
        conn,
        USER_ID,
        _offline_client(),
        today=date(2026, 1, 1),
        horizon_days=0,
        base_currency="PLN",
    )

    # 100.00 EUR @ 4.30 → 430.00 PLN = 43000 minor.
    assert len(series.days) == 1
    assert series.days[0].totals_base_minor == 43000


def test_editing_a_planned_row_changes_forecast_output(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    account_id = make_account(opening_balance=100000)
    category_id = make_category()
    planned_id = make_planned(
        account_id=account_id,
        category_id=category_id,
        amount=5000,
        operation_date=date(2026, 1, 20),
    )
    client = _offline_client()
    before = forecast_service.forecast(
        conn, USER_ID, client, today=date(2026, 1, 1), horizon_days=30, base_currency="PLN"
    )

    planned_repo.update(conn, USER_ID, planned_id, PatchPlannedTransaction(amount=9000))

    after = forecast_service.forecast(
        conn, USER_ID, client, today=date(2026, 1, 1), horizon_days=30, base_currency="PLN"
    )
    assert before != after
