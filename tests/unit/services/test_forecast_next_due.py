"""Forecast honours ``rule.next_due`` (T-FIX3, ADR-0087).

An early-promoted recurring occurrence is already a transaction (so it is in
the starting balance); the forecast must not project it again.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import httpx
import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
)
from budget_planner.repositories import accounts, categories, planned, recurring
from budget_planner.services import forecast as forecast_svc
from budget_planner.services.recurring import PromotionEdits, promote_recurring

USER_ID = 1
TODAY = date(2026, 11, 6)
NOV = date(2026, 11, 1)
DEC = date(2026, 12, 1)
SALARY = 2_950_000
REMAINING = 70_000


def _dead_client() -> httpx.Client:
    def _h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline in tests")

    return httpx.Client(transport=httpx.MockTransport(_h), base_url="https://x")


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    acct = accounts.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    return {"acct": acct, "salary": salary, "rent": rent}


def _rule(
    conn: sqlite3.Connection,
    world: dict[str, int],
    *,
    cat: str,
    day: int,
    amount: int,
    formula: AmountFormula | None = None,
) -> int:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 7, day),
            category_id=world[cat],
            account_id=world["acct"],
            default_amount=amount,
            day_of_month=day,
            amount_formula=formula,
        ),
    )
    # create_rule anchors next_due on the wall clock; pin it for determinism.
    recurring.set_next_due(
        conn, USER_ID, rule.id, next_due=date(2026, 11, day), last_promoted_date=None
    )
    return rule.id


def _promote_early(conn: sqlite3.Connection, rule_id: int) -> None:
    promote_recurring(conn, USER_ID, rule_id, PromotionEdits(operation_date=TODAY))


def _plan_remaining(conn: sqlite3.Connection, world: dict[str, int], cat: str) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 20),
            category_id=world[cat],
            account_id=world["acct"],
            amount=REMAINING,
            description="remaining",
        ),
    )


def _monthly(conn: sqlite3.Connection, months: int = 3) -> forecast_svc.MonthlySeries:
    with _dead_client() as http:
        return forecast_svc.forecast_monthly(conn, USER_ID, http, TODAY, months, "PLN")


def _row(series: forecast_svc.MonthlySeries, month: date) -> forecast_svc.MonthlyPoint:
    return next(r for r in series.months if r.month == month)


def test_early_promoted_income_not_reprojected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rid = _rule(conn, world, cat="salary", day=7, amount=SALARY)
    _plan_remaining(conn, world, "salary")
    _promote_early(conn, rid)
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == REMAINING
    assert _row(series, DEC).income_base_minor == SALARY


def test_early_promoted_formula_income_not_reprojected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rule(conn, world, cat="rent", day=20, amount=2 * SALARY)
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=5_000, source_category_ids=(world["rent"],)),)
    )
    rid = _rule(conn, world, cat="salary", day=7, amount=0, formula=formula)
    _plan_remaining(conn, world, "salary")
    _promote_early(conn, rid)
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == REMAINING
    assert _row(series, DEC).income_base_minor == SALARY


def test_early_promoted_expense_not_reprojected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rid = _rule(conn, world, cat="rent", day=7, amount=300_000)
    _promote_early(conn, rid)
    series = _monthly(conn)
    assert _row(series, NOV).expense_base_minor == 0
    assert _row(series, DEC).expense_base_minor == 300_000


def test_unpromoted_rule_still_projected(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _rule(conn, world, cat="salary", day=7, amount=SALARY)
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == SALARY


def test_on_time_promotion_matches_early(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rid = _rule(conn, world, cat="salary", day=5, amount=SALARY)
    promote_recurring(conn, USER_ID, rid, PromotionEdits(operation_date=date(2026, 11, 5)))
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == 0
    assert _row(series, DEC).income_base_minor == SALARY


def test_skipped_occurrence_stays_excluded(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rid = _rule(conn, world, cat="salary", day=7, amount=SALARY)
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rid, occurrence_date=date(2026, 11, 7), state=OverrideState.SKIPPED
        ),
    )
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == 0
    assert _row(series, DEC).income_base_minor == SALARY


def test_date_override_cannot_resurrect_promoted_occurrence(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Filtering is by canonical date: a stray override on a consumed
    occurrence (canonical 11-07 < next_due 12-07) stays consumed."""
    rid = _rule(conn, world, cat="salary", day=7, amount=SALARY)
    _promote_early(conn, rid)
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rid,
            occurrence_date=date(2026, 11, 7),
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 11, 25),
        ),
    )
    assert _row(_monthly(conn), NOV).income_base_minor == 0


def test_date_override_on_unpromoted_occurrence_moves_it(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rid = _rule(conn, world, cat="salary", day=7, amount=SALARY)
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rid,
            occurrence_date=date(2026, 11, 7),
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 12, 2),
        ),
    )
    series = _monthly(conn)
    assert _row(series, NOV).income_base_minor == 0
    assert _row(series, DEC).income_base_minor == 2 * SALARY


def test_daily_eom_balance_counts_early_promoted_once(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rid = _rule(conn, world, cat="salary", day=7, amount=SALARY)
    _promote_early(conn, rid)
    with _dead_client() as http:
        daily = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    by_date = {d.on_date: d.totals_base_minor for d in daily.days}
    # Promoted salary is already in the balance; 11-07 adds nothing.
    assert by_date[date(2026, 11, 8)] == by_date[TODAY] == SALARY
    assert by_date[date(2026, 12, 6)] == SALARY
