"""T-D52 — available credit -> target balance conversion."""

from __future__ import annotations

import pytest

from budget_planner.services import reconciliation


@pytest.mark.parametrize(
    ("limit", "available", "expected"),
    [(500_000, 400_000, -100_000), (500_000, 0, -500_000), (500_000, 500_000, 0)],
)
def test_available_to_target_balance(limit: int, available: int, expected: int) -> None:
    assert reconciliation.available_to_target_balance(limit, available) == expected


@pytest.mark.parametrize(("limit", "available"), [(500_000, -1), (500_000, 500_001), (0, 0)])
def test_available_to_target_balance_rejects_invalid(limit: int, available: int) -> None:
    with pytest.raises(reconciliation.InvalidAvailableError):
        reconciliation.available_to_target_balance(limit, available)
