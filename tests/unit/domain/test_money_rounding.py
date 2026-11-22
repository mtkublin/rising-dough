"""T-Q281 / ADR-0006 amendment 2026-11-22: the two rounding helpers, one mode (half to even)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from budget_planner.domain import money
from budget_planner.domain.money import (
    format_whole,
    percent_to_bps,
    round_div,
    round_scaled,
    to_minor_units,
)

SRC = Path(money.__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (5, 2, 2),  # 2.5 -> even
        (7, 2, 4),  # 3.5 -> even
        (250, 100, 2),
        (350, 100, 4),
        (-5, 2, -2),
        (-7, 2, -4),
        (10, 3, 3),
        (11, 3, 4),
        (0, 7, 0),
    ],
)
def test_round_div_rounds_ties_to_even(numerator: int, denominator: int, expected: int) -> None:
    assert round_div(numerator, denominator) == expected


def test_round_div_rejects_zero_denominator() -> None:
    with pytest.raises(ZeroDivisionError):
        round_div(1, 0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("2.5"), 2),
        (Decimal("3.5"), 4),
        (Decimal("-2.5"), -2),
        (Decimal("2.4999"), 2),
        (Decimal("2.5001"), 3),
    ],
)
def test_round_scaled_rounds_ties_to_even(value: Decimal, expected: int) -> None:
    assert round_scaled(value) == expected


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        (Decimal("0.025"), "PLN", 2),  # 2.5 minor -> 2 (HALF_UP gave 3)
        (Decimal("0.035"), "PLN", 4),
        (Decimal("2.5"), "JPY", 2),
        (Decimal("3.5"), "JPY", 4),
        (Decimal("0.0025"), "KWD", 2),
    ],
)
def test_to_minor_units_ties_to_even(amount: Decimal, currency: str, expected: int) -> None:
    assert to_minor_units(amount, currency) == expected


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(Decimal("0.025"), 2), (Decimal("0.035"), 4), (Decimal("12.345"), 1234)],
)
def test_percent_to_bps_ties_to_even(percent: Decimal, expected: int) -> None:
    assert percent_to_bps(percent) == expected


@pytest.mark.parametrize(
    ("minor", "expected"),
    [(250, "2"), (350, "4"), (150, "2"), (-250, "-2"), (-50, "0")],
)
def test_format_whole_ties_to_even(minor: int, expected: str) -> None:
    assert format_whole(minor, "PLN") == expected


def test_no_half_up_symbol_or_mode_argument_remains_in_src() -> None:
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "HALF_UP" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
    assert not hasattr(money, "HALF_UP")
    assert not hasattr(money, "RoundingMode")


@pytest.mark.parametrize(("minor", "expected"), [(5, 2), (7, 4), (-5, -2)])
def test_rescale_minor_fx_tie_at_four_decimal_rate(minor: int, expected: int) -> None:
    # 5 grosz * 0.5000 = 2.5 cents -> 2; 7 * 0.5000 = 3.5 -> 4
    assert money.rescale_minor(minor, "PLN", "EUR", Decimal("0.5000")) == expected
