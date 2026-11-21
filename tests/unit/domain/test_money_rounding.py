"""T-Q229 / ADR-0006 amendment: the two rounding helpers and their explicit mode."""

from __future__ import annotations

from decimal import Decimal

import pytest

from budget_planner.domain.money import HALF_EVEN, HALF_UP, RoundingMode, round_div, round_scaled


@pytest.mark.parametrize(
    ("numerator", "denominator", "mode", "expected"),
    [
        (5, 2, HALF_EVEN, 2),  # 2.5 -> even
        (7, 2, HALF_EVEN, 4),  # 3.5 -> even
        (5, 2, HALF_UP, 3),
        (7, 2, HALF_UP, 4),
        (-5, 2, HALF_UP, -3),  # away from zero
        (-5, 2, HALF_EVEN, -2),
        (10, 3, HALF_EVEN, 3),
        (11, 3, HALF_UP, 4),
        (0, 7, HALF_EVEN, 0),
    ],
)
def test_round_div_rounds_ties_per_explicit_mode(
    numerator: int, denominator: int, mode: RoundingMode, expected: int
) -> None:
    assert round_div(numerator, denominator, mode=mode) == expected


def test_round_div_rejects_zero_denominator() -> None:
    with pytest.raises(ZeroDivisionError):
        round_div(1, 0, mode=HALF_EVEN)


@pytest.mark.parametrize(
    ("value", "mode", "expected"),
    [
        (Decimal("2.5"), HALF_EVEN, 2),
        (Decimal("3.5"), HALF_EVEN, 4),
        (Decimal("2.5"), HALF_UP, 3),
        (Decimal("-2.5"), HALF_UP, -3),
        (Decimal("2.4999"), HALF_UP, 2),
    ],
)
def test_round_scaled_rounds_decimal_to_integer(
    value: Decimal, mode: RoundingMode, expected: int
) -> None:
    assert round_scaled(value, mode=mode) == expected
