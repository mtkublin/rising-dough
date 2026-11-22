"""Canonical direction-to-sign rule (ADR-0008, T-Q227, Q-036)."""

from __future__ import annotations

import pytest

from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import SignedLeg, signed_legs


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (Direction.INCOME, (SignedLeg(account_id=1, amount_minor=500),)),
        (Direction.EXPENSE, (SignedLeg(account_id=1, amount_minor=-500),)),
        (Direction.ADJUSTMENT, (SignedLeg(account_id=1, amount_minor=500),)),
        (
            Direction.TRANSIT,
            (SignedLeg(account_id=1, amount_minor=-500), SignedLeg(account_id=2, amount_minor=500)),
        ),
    ],
)
def test_signed_legs_matrix(direction: Direction, expected: tuple[SignedLeg, ...]) -> None:
    assert signed_legs(direction, 500, 1, 2) == expected


def test_adjustment_is_pre_signed() -> None:
    assert signed_legs(Direction.ADJUSTMENT, -500, 1, None) == (
        SignedLeg(account_id=1, amount_minor=-500),
    )


def test_transit_without_destination_raises() -> None:
    with pytest.raises(ValueError, match=r"^transit transaction missing dest_account_id$"):
        signed_legs(Direction.TRANSIT, 5, 1, None)
