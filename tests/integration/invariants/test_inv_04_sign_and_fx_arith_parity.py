# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-4: copies of the same arithmetic must agree (guards the Q-036 / Q-007 consolidation once it lands)."""

from __future__ import annotations

import datetime as dt
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.transactions import Transaction
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import account_planned, balance, forecast, fx, ledger_totals
from budget_planner.web import today_data
from tests.integration.invariants.conftest import offline_http


def _transit_txn() -> Transaction:
    now = dt.datetime.now(dt.UTC)
    return Transaction(
        id=1,
        user_id=1,
        operation_date=date(2026, 11, 1),
        category_id=1,
        account_id=1,
        dest_account_id=2,
        amount=1000,
        description="",
        promoted_from_planned_id=None,
        promoted_from_recurring_rule_id=None,
        promoted_from_recurring_date=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


@pytest.mark.parametrize("direction", [d for d in Direction if d is not Direction.ADJUSTMENT])
def test_4a_source_leg_is_identical_across_implementations(direction: Direction) -> None:
    txn = _transit_txn()
    legs_balance = {leg.account_id: leg.amount_minor for leg in balance.signed_legs(txn, direction)}
    legs_forecast = {
        e.account_id: e.amount_minor
        for e in forecast._signed_events_for_direction(direction, date(2026, 11, 1), 1, 2, 1000)
    }
    legs_planned = dict(account_planned._legs(direction, 1, 2, 1000))
    assert ledger_totals.signed_effect(1000, direction) is not None
    assert legs_balance.get(1, 0) == legs_forecast.get(1, 0) == legs_planned.get(1, 0)


def test_4a_adjustment_is_counted_by_balance_and_skipped_by_forecast() -> None:
    """Documented asymmetry (ADR-0011): balance counts adjustments, forecast and planned skip them."""
    legs_balance = balance.signed_legs(_transit_txn(), Direction.ADJUSTMENT)
    events = forecast._signed_events_for_direction(
        Direction.ADJUSTMENT, date(2026, 11, 1), 1, 2, 1000
    )
    assert (
        legs_balance and not events and not account_planned._legs(Direction.ADJUSTMENT, 1, 2, 1000)
    )


def test_4b_four_fx_arithmetic_copies_agree(seeded: sqlite3.Connection) -> None:
    day = date(2026, 11, 1)
    grid = (
        ("EUR", "PLN", Decimal("4.2655")),
        ("JPY", "PLN", Decimal("0.0275")),
        ("PLN", "JPY", Decimal("36.3636")),
    )
    for src, dst, rate in grid:
        fx_repo.upsert_rate(seeded, NewFxRate(date=day, from_ccy=src, to_ccy=dst, rate=rate))
    divergent = []
    for src, dst, rate in grid:
        for amount in [*range(-300, 301, 7), 1, 5, 50, 12345, 99_999_999]:
            results = {
                fx.convert(seeded, offline_http(), amount, day, src, dst),
                fx.convert_cached(seeded, amount, day, src, dst),
                forecast._convert_native_to_base(amount, src, dst, {src: rate}),
                today_data._convert_minor(amount, src, dst, rate),
            }
            if len(results) != 1:
                divergent.append((src, dst, amount, results))
    assert not divergent, divergent[:5]
