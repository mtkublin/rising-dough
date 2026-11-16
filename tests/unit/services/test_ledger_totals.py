"""T-D48 — ledger day net respects ADR-0008 signs (adjustment pre-signed)."""

from __future__ import annotations

import datetime as dt

from budget_planner.domain.enums import Direction
from budget_planner.services.ledger_totals import day_nets, signed_effect

D = dt.date(2026, 11, 2)


def _ident(amount: int, day: dt.date, ccy: str) -> int:
    return amount


def test_negative_reconciliation_plus_expenses_sums_negative() -> None:
    rows = [
        (D, -70000, Direction.ADJUSTMENT, "PLN"),
        (D, 10000, Direction.EXPENSE, "PLN"),
        (D, 5000, Direction.EXPENSE, "PLN"),
    ]
    assert day_nets(rows, _ident) == {D: -85000}


def test_positive_reconciliation_and_income() -> None:
    rows = [
        (D, 20000, Direction.ADJUSTMENT, "PLN"),
        (D, 30000, Direction.INCOME, "PLN"),
        (D, 5000, Direction.EXPENSE, "PLN"),
    ]
    assert day_nets(rows, _ident) == {D: 45000}


def test_transit_excluded_and_uncategorised_ignored() -> None:
    rows = [(D, 9999, Direction.TRANSIT, "PLN"), (D, 5, None, "PLN")]
    assert day_nets(rows, _ident) == {D: 0}


def test_converts_each_row_to_base_with_sign_preserved() -> None:
    rows = [(D, -1000, Direction.ADJUSTMENT, "EUR"), (D, 100, Direction.EXPENSE, "PLN")]
    result = day_nets(rows, lambda a, _d, c: a * 4 if c == "EUR" else a)
    assert result == {D: -4100}


def test_signed_effect_matrix() -> None:
    assert signed_effect(5, Direction.INCOME) == 5
    assert signed_effect(5, Direction.EXPENSE) == -5
    assert signed_effect(-5, Direction.ADJUSTMENT) == -5
    assert signed_effect(5, Direction.TRANSIT) == 0
