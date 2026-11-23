"""Unit tests for :func:`services.today.afford` (T-R40, ADR-0056 §3)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import preferences as preferences_svc, today as today_svc

USER_ID = 1


def _seed_budget(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed one expense category + default budget + one spent txn.

    Totals (minor units): budgeted = 30000, spent = 10000, remaining = 20000.
    """
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=cat.id, amount=30_000))
    transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 1),
            category_id=cat.id,
            account_id=acc.id,
            amount=10_000,
            description="",
        ),
    )
    return {"account_id": acc.id, "category_id": cat.id}


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> dict[str, int]:
    return _seed_budget(conn)


class TestAfford:
    def test_zero_amount_matches_baseline(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        result = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            0,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert result.per_day_minor >= 0
        assert result.delta_minor == 0
        assert result.pace_tag in ("on_track", "tight", "over_limit")

    def test_positive_amount_lowers_per_day(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        baseline = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            0,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        hypothetical = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            5_000,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert hypothetical.per_day_minor <= baseline.per_day_minor
        assert hypothetical.delta_minor <= 0

    def test_amount_greater_than_remaining_clamps_to_zero_and_over_limit(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        result = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            999_999,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert result.per_day_minor == 0
        assert result.pace_tag == "over_limit"

    def test_negative_amount_raises(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        with pytest.raises(ValueError):
            today_svc.afford(
                conn,
                USER_ID,
                date(2026, 1, 10),
                -1,
                base_currency="PLN",
                display_timezone=DEFAULT_DISPLAY_TIMEZONE,
            )

    def test_zero_budget_month_returns_zero_per_day(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        # No budgets seeded → remaining stays 0.
        result = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            0,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert result.per_day_minor == 0
        assert result.pace_tag == "over_limit"

    def test_pace_tag_tight_fires_between_half_and_full_baseline(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        # Budget 30000 - 10000 spent = 20000 remaining / 22 days ≈ 909/day.
        # A hypothetical 15000 lowers remaining to 5000 / 22 ≈ 227/day,
        # which is well under half of baseline → tight.
        tight = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 10),
            15_000,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert tight.pace_tag in {"tight", "over_limit"}

    def test_days_left_floored_at_one(
        self,
        conn: sqlite3.Connection,
        seeded: dict[str, int],
    ) -> None:
        # Any today should produce days_left >= 1 (floor).
        result = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 1, 31),
            0,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        assert result.days_left >= 1

    def test_baseline_follows_fiscal_month_before_current_month_anchor(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        # ADR-0064: baseline must match the Today hero, which uses the fiscal
        # cycle. When today falls on Feb 2 but the Feb paycheck has not landed
        # yet, the fiscal month is January — so the January budget/spent must
        # drive the per-day figure, not an empty February.
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        expense = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        income = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        preferences_svc.set_income_anchor_category_id(conn, 1, income.id)
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 1, 5),
                category_id=income.id,
                account_id=acc.id,
                amount=100_000,
                description="",
            ),
        )
        budgets_repo.set_default(
            conn, USER_ID, NewBudgetDefault(category_id=expense.id, amount=30_000)
        )
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 1, 20),
                category_id=expense.id,
                account_id=acc.id,
                amount=10_000,
                description="",
            ),
        )
        # Today = Feb 2; no February anchor landed → fiscal month = January.
        baseline = today_svc.afford(
            conn,
            USER_ID,
            date(2026, 2, 2),
            0,
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        # January remaining = 30000 - 10000 = 20000 (non-zero) → per_day > 0.
        assert baseline.per_day_minor > 0


def _afford(
    conn: sqlite3.Connection, amount_minor: int, user_id: int = USER_ID
) -> today_svc.AffordResult:
    return today_svc.afford(
        conn,
        user_id,
        date(2026, 1, 10),
        amount_minor,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )


class TestUnclampedAndOver:
    """T-UR34e (G4): unclamped per-day and the over amount; remaining = 20_000."""

    def test_under_remaining(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        days = _afford(conn, 0).days_left
        result = _afford(conn, 5_000)
        assert result.over_minor == 0
        assert result.unclamped_per_day_minor == today_svc.daily_share_minor(15_000, days)
        assert result.unclamped_per_day_minor == result.per_day_minor

    def test_exactly_remaining(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        result = _afford(conn, 20_000)
        assert result.over_minor == 0
        assert result.unclamped_per_day_minor == 0
        assert result.per_day_minor == 0

    def test_over_remaining(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        days = _afford(conn, 0).days_left
        result = _afford(conn, 30_000)
        assert result.over_minor == 10_000
        assert result.unclamped_per_day_minor == today_svc.daily_share_minor(-10_000, days)
        assert result.unclamped_per_day_minor < 0
        assert result.per_day_minor == 0
        assert result.pace_tag == "over_limit"

    def test_no_budget_everything_is_over(self, conn: sqlite3.Connection) -> None:
        result = _afford(conn, 2_500)
        assert result.over_minor == 2_500
        assert result.unclamped_per_day_minor < 0

    def test_second_user_data_is_ignored(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        other = _afford(conn, 30_000, user_id=USER_ID + 1)
        assert other.over_minor == 30_000
        assert _afford(conn, 30_000).over_minor == 10_000


def test_invalid_message_text() -> None:
    assert today_svc.AFFORD_INVALID_MESSAGE == "Enter an amount, like 250.00"
