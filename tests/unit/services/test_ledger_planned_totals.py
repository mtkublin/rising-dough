"""T-Q209 — planned strip and recurring summary are signed by direction (ADR-0008, Q-010)."""

from __future__ import annotations

from types import SimpleNamespace

from budget_planner.domain.enums import Cadence, Direction
from budget_planner.services.ledger_totals import planned_totals, recurring_monthly_totals


def _planned(amount: int, direction: Direction | None, promoted: bool = False) -> dict[str, object]:
    cat = SimpleNamespace(direction=direction) if direction else None
    return {"amount_minor": amount, "category": cat, "is_promoted": promoted}


def _rule(amount: int, cadence: Cadence | None, direction: Direction | None) -> dict[str, object]:
    cat = SimpleNamespace(direction=direction) if direction else None
    return {"effective_amount_minor": amount, "cadence": cadence, "category": cat}


def test_planned_total_nets_income_and_expense() -> None:
    rows = [
        _planned(500000, Direction.INCOME),
        _planned(120050, Direction.EXPENSE),
        _planned(30000, Direction.EXPENSE),
    ]
    totals = planned_totals(rows, "PLN")
    assert totals.count == 3
    assert totals.net_minor == 349950
    assert totals.net_display == "3,499.50 PLN"


def test_planned_total_negative_net_and_promoted_excluded() -> None:
    rows = [
        _planned(10000, Direction.INCOME),
        _planned(25000, Direction.EXPENSE),
        _planned(999999, Direction.EXPENSE, promoted=True),
    ]
    totals = planned_totals(rows, "PLN")
    assert totals.count == 2
    assert totals.net_minor == -15000
    assert totals.net_display == "-150.00 PLN"


def test_planned_total_skips_transit_and_uncategorised() -> None:
    rows = [_planned(7000, Direction.TRANSIT), _planned(5, None)]
    assert planned_totals(rows, "PLN").net_minor == 0


def test_recurring_totals_route_by_direction_with_cadence_divisor() -> None:
    rows = [
        _rule(100000, Cadence.MONTHLY, Direction.EXPENSE),
        _rule(30000, Cadence.QUARTERLY, Direction.EXPENSE),
        _rule(120000, Cadence.YEARLY, Direction.INCOME),
        _rule(400000, None, Direction.INCOME),
        _rule(1, Cadence.MONTHLY, None),
    ]
    totals = recurring_monthly_totals(rows, "PLN")
    assert totals.monthly_out_minor == 110000
    assert totals.monthly_in_minor == 410000
    assert totals.monthly_out_display == "1,100.00 PLN"
    assert totals.monthly_in_display == "4,100.00 PLN"
