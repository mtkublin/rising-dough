"""Owners for means, category sums and the budget tier pick (T-Q227, Q-008, Q-075)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from budget_planner.domain.transactions import Transaction
from budget_planner.services.aggregates import mean_minor, sum_by_category
from budget_planner.services.budget import pick_tier

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _txn(category_id: int, amount: int) -> Transaction:
    return Transaction(
        id=1,
        user_id=1,
        operation_date=date(2026, 1, 1),
        category_id=category_id,
        account_id=1,
        dest_account_id=None,
        amount=amount,
        description="",
        promoted_from_planned_id=None,
        promoted_from_recurring_rule_id=None,
        promoted_from_recurring_date=None,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def test_mean_minor_half_even_and_empty() -> None:
    assert mean_minor(5, 2) == 2
    assert mean_minor(7, 2) == 4
    assert mean_minor(10, 0) == 0


def test_sum_by_category_applies_converter() -> None:
    txns = [_txn(1, 100), _txn(1, 50), _txn(2, 30)]
    assert sum_by_category(txns, lambda t: t.amount * 2) == {1: 300, 2: 60}


@pytest.mark.parametrize(
    ("tiers", "expected"),
    [
        ((10, 20, 30), (10, "one_off")),
        ((None, 20, 30), (20, "recurring")),
        ((None, None, 30), (30, "default")),
        ((0, 20, 30), (0, "one_off")),
        ((None, None, None), (None, "unset")),
    ],
)
def test_pick_tier(tiers: tuple[int | None, int | None, int | None], expected: object) -> None:
    assert pick_tier(*tiers) == expected
