"""T-Q209 — planned strip and recurring summary are signed by direction (ADR-0008, Q-010)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from budget_planner.domain.enums import Cadence, Direction
from budget_planner.services.ledger_totals import planned_totals, recurring_monthly_totals


def _same(amount: int, _day: dt.date, _ccy: str) -> int:
    return amount


def _planned(amount: int, direction: Direction | None, promoted: bool = False) -> dict[str, object]:
    cat = SimpleNamespace(direction=direction) if direction else None
    return {
        "amount_minor": amount,
        "category": cat,
        "is_promoted": promoted,
        "operation_date": dt.date(2026, 11, 1),
        "currency": "PLN",
    }


def _rule(amount: int, cadence: Cadence, direction: Direction | None) -> dict[str, object]:
    cat = SimpleNamespace(direction=direction) if direction else None
    return {
        "effective_amount_minor": amount,
        "cadence": cadence,
        "category": cat,
        "next_due": dt.date(2026, 11, 1),
        "currency": "PLN",
    }


def test_planned_total_nets_income_and_expense() -> None:
    rows = [
        _planned(500000, Direction.INCOME),
        _planned(120050, Direction.EXPENSE),
        _planned(30000, Direction.EXPENSE),
    ]
    totals = planned_totals(rows, "PLN", _same)
    assert totals.count == 3
    assert totals.net_minor == 349950
    assert totals.net_display == "3,499.50 PLN"


def test_planned_total_negative_net_and_promoted_excluded() -> None:
    rows = [
        _planned(10000, Direction.INCOME),
        _planned(25000, Direction.EXPENSE),
        _planned(999999, Direction.EXPENSE, promoted=True),
    ]
    totals = planned_totals(rows, "PLN", _same)
    assert totals.count == 2
    assert totals.net_minor == -15000
    assert totals.net_display == "-150.00 PLN"


def test_planned_total_skips_transit_and_uncategorised() -> None:
    rows = [_planned(7000, Direction.TRANSIT), _planned(5, None)]
    assert planned_totals(rows, "PLN", _same).net_minor == 0


def test_recurring_totals_route_by_direction_with_cadence_divisor() -> None:
    rows = [
        _rule(100000, Cadence.MONTHLY, Direction.EXPENSE),
        _rule(30000, Cadence.QUARTERLY, Direction.EXPENSE),
        _rule(120000, Cadence.YEARLY, Direction.INCOME),
        _rule(400000, Cadence.MONTHLY, Direction.INCOME),
        _rule(1, Cadence.MONTHLY, None),
    ]
    totals = recurring_monthly_totals(rows, "PLN", _same)
    assert totals.monthly_out_minor == 110000
    assert totals.monthly_in_minor == 410000
    assert totals.monthly_out_display == "1,100.00 PLN"
    assert totals.monthly_in_display == "4,100.00 PLN"


def test_recurring_totals_reject_unknown_cadence() -> None:
    row = {"effective_amount_minor": 1, "cadence": "weekly", "category": None}
    with pytest.raises(ValueError, match="weekly"):
        recurring_monthly_totals([row], "PLN", _same)


def _eur_at_4_30(amount: int, _day: dt.date, ccy: str) -> int:
    return amount * 430 // 100 if ccy == "EUR" else amount


def test_recurring_totals_convert_eur_rule_to_base() -> None:
    eur = {**_rule(10000, Cadence.MONTHLY, Direction.EXPENSE), "currency": "EUR"}
    pln = _rule(5000, Cadence.MONTHLY, Direction.INCOME)
    totals = recurring_monthly_totals([eur, pln], "PLN", _eur_at_4_30)
    assert totals.monthly_out_minor == 43000
    assert totals.monthly_in_minor == 5000
    assert totals.monthly_out_display == "430.00 PLN"


def test_planned_totals_convert_eur_row_to_base() -> None:
    eur = {**_planned(10000, Direction.INCOME), "currency": "EUR"}
    totals = planned_totals([eur, _planned(3000, Direction.EXPENSE)], "PLN", _eur_at_4_30)
    assert totals.net_minor == 40000
    assert totals.net_display == "400.00 PLN"
