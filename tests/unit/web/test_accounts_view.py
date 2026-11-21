"""T-Q256 — credit_utilisation view-model values (Q-070)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from budget_planner.domain.accounts import Account
from budget_planner.web.accounts_view import CreditUtilisation, credit_utilisation

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _acc(*, limit: int | None, liability: bool = True) -> Account:
    return Account(
        id=1,
        user_id=1,
        name="Visa",
        type=None,
        currency="PLN",
        opening_balance=0,
        is_liability=liability,
        credit_limit_minor=limit,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def test_partial_use_exact_values() -> None:
    util = credit_utilisation(_acc(limit=500_000), -123_456)
    assert util == CreditUtilisation(
        limit_minor=500_000,
        used_minor=123_456,
        available_minor=376_544,
        over_limit_minor=0,
        used_pct=24,
        bar_pct=24,
    )


def test_over_limit_caps_bar_and_reports_excess() -> None:
    util = credit_utilisation(_acc(limit=100_000), -150_000)
    assert util is not None
    assert (util.used_minor, util.available_minor, util.over_limit_minor) == (
        150_000,
        0,
        50_000,
    )
    assert (util.used_pct, util.bar_pct) == (150, 100)


def test_positive_balance_means_nothing_used() -> None:
    util = credit_utilisation(_acc(limit=100_000), 25_000)
    assert util is not None
    assert (util.used_minor, util.available_minor, util.used_pct) == (0, 100_000, 0)


@pytest.mark.parametrize("limit", [0, None, -5])
def test_zero_or_missing_limit_has_no_utilisation(limit: int | None) -> None:
    assert credit_utilisation(_acc(limit=limit), -10_000) is None


def test_non_liability_has_no_utilisation() -> None:
    assert credit_utilisation(_acc(limit=100_000, liability=False), -10_000) is None
