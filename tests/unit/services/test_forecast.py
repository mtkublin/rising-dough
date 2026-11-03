"""Tests for the forecast service (T-025)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault, NewBudgetOneOffOverride
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts,
    budgets as budgets_repo,
    categories,
    fx as fx_repo,
    planned,
    recurring,
    transactions as transactions_repo,
)
from budget_planner.services import forecast as forecast_svc

USER_ID = 1

_API = "https://api.frankfurter.app"


def _dead_client() -> httpx.Client:
    """HTTP client that fails on any request. Forces FX cache usage."""

    def _h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline in tests")

    return httpx.Client(transport=httpx.MockTransport(_h), base_url=_API)


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=_API)


TODAY = date(2026, 10, 23)


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    """A deterministic mini-world with every direction + a monthly rule."""
    a1 = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=100_000)
    ).id
    a2 = accounts.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id
    a3 = accounts.create(
        conn, USER_ID, NewAccount(name="EUR Cash", currency="EUR", opening_balance=50_000)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    transit = categories.find_by_name(conn, USER_ID, "Transit")
    reconciliation = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert transit is not None and reconciliation is not None

    # Planned expense inside horizon on A1
    p1 = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 10, 25),
            category_id=groceries,
            account_id=a1,
            amount=10_000,
            description="groceries",
        ),
    ).id
    # Planned transit A1 -> A2
    p2 = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 5),
            category_id=transit.id,
            account_id=a1,
            dest_account_id=a2,
            amount=20_000,
            description="savings sweep",
        ),
    ).id
    # Planned income
    p3 = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 15),
            category_id=salary,
            account_id=a1,
            amount=800_000,
            description="payday",
        ),
    ).id
    # Monthly Rent rule, start 2026-10-01, amount 300_000 on A1
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 10, 1),
            category_id=rent,
            account_id=a1,
            default_amount=300_000,
            default_description="rent",
        ),
    ).id
    # Cache EUR->PLN rate for TODAY
    fx_repo.upsert_rate(
        conn,
        NewFxRate(date=TODAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
    )
    return {
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "groceries": groceries,
        "salary": salary,
        "rent": rent,
        "transit": transit.id,
        "reconciliation": reconciliation.id,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "rule": rule,
    }


def _point_for(day: forecast_svc.DayPoint, account_id: int) -> forecast_svc.AccountBalancePoint:
    for p in day.by_account:
        if p.account_id == account_id:
            return p
    raise AssertionError(f"account {account_id} missing from day {day.on_date}")


def _day_for(series: forecast_svc.ForecastSeries, on: date) -> forecast_svc.DayPoint:
    for d in series.days:
        if d.on_date == on:
            return d
    raise AssertionError(f"day {on} missing from series")


# ---------------------------------------------------------------------------
# shape / contract
# ---------------------------------------------------------------------------
def test_series_length_matches_horizon(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 60, "PLN")
    assert len(series.days) == 61
    assert series.start_date == TODAY
    assert series.end_date == TODAY + timedelta(days=60)
    assert series.base_currency == "PLN"


def test_horizon_zero_returns_single_anchor_day(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _ = world
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 0, "PLN")
    assert len(series.days) == 1
    assert series.days[0].on_date == TODAY


def test_end_of_horizon_date(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 60, "PLN")
    assert series.days[-1].on_date == TODAY + timedelta(days=60)


# ---------------------------------------------------------------------------
# anchor
# ---------------------------------------------------------------------------
def test_day_zero_anchor_matches_derive_balance(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    day0 = series.days[0]
    p = _point_for(day0, world["a1"])
    assert p.native_minor == 100_000  # A1 opening_balance
    p3 = _point_for(day0, world["a3"])
    assert p3.native_minor == 50_000  # A3 opening_balance in EUR minor
    # Base conversion: A3 50_000 EUR cents * 4.30 = 215_000 PLN cents.
    assert p3.base_minor == 215_000


def test_day_zero_total_sums_per_account_base(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 10, "PLN")
    day0 = series.days[0]
    expected = (
        _point_for(day0, world["a1"]).base_minor
        + _point_for(day0, world["a2"]).base_minor
        + _point_for(day0, world["a3"]).base_minor
    )
    assert day0.totals_base_minor == expected
    # Known from fixtures: 100_000 + 0 + 215_000.
    assert day0.totals_base_minor == 315_000


# ---------------------------------------------------------------------------
# event application
# ---------------------------------------------------------------------------
def test_expense_drops_balance_on_operation_date(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 10, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 24)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 10, 25)), world["a1"]).native_minor
    assert prev - curr == 10_000


def test_transit_moves_funds_on_operation_date(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev_a1 = _point_for(_day_for(series, date(2026, 11, 4)), world["a1"]).native_minor
    curr_a1 = _point_for(_day_for(series, date(2026, 11, 5)), world["a1"]).native_minor
    prev_a2 = _point_for(_day_for(series, date(2026, 11, 4)), world["a2"]).native_minor
    curr_a2 = _point_for(_day_for(series, date(2026, 11, 5)), world["a2"]).native_minor
    assert prev_a1 - curr_a1 == 20_000
    assert curr_a2 - prev_a2 == 20_000


def test_income_adds_on_operation_date(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev = _point_for(_day_for(series, date(2026, 11, 14)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 15)), world["a1"]).native_minor
    assert curr - prev == 800_000


def test_virtual_recurring_applied(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 31)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 1)), world["a1"]).native_minor
    assert prev - curr == 300_000


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------
def test_dedup_prefers_persisted_planned_over_virtual(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # Materialise the Nov 1 occurrence as a persisted planned row.
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 1),
            category_id=world["rent"],
            account_id=world["a1"],
            amount=300_000,
            description="rent (edited)",
            recurring_rule_id=world["rule"],
            occurrence_date=date(2026, 11, 1),
        ),
    )
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 31)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 1)), world["a1"]).native_minor
    # Only one 300_000 drop, not two.
    assert prev - curr == 300_000


# ---------------------------------------------------------------------------
# FX aggregation
# ---------------------------------------------------------------------------
def test_fx_aggregates_eur_account_to_base(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 10, "PLN")
    day0 = series.days[0]
    a3 = _point_for(day0, world["a3"])
    assert a3.native_minor == 50_000
    # 50_000 * 4.30 = 215_000, ROUND_HALF_EVEN of exact.
    assert a3.base_minor == 215_000


def test_fx_fallback_uses_latest_cached_rate(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # Replace TODAY rate with a yesterday rate.
    conn.execute("DELETE FROM fx_rates WHERE date = ?", (TODAY.isoformat(),))
    fx_repo.upsert_rate(
        conn,
        NewFxRate(
            date=TODAY - timedelta(days=1),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.00"),
        ),
    )
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 5, "PLN")
    a3 = _point_for(series.days[0], world["a3"])
    assert a3.base_minor == 200_000  # 50_000 * 4.00


def test_base_currency_identity_no_fx_calls(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _ = world
    hits: list[httpx.Request] = []

    def _h(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return httpx.Response(500)

    with _mock_client(_h) as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 5, "PLN")
    # Only EUR->PLN would need remote; today's rate is already cached. For a1/a2 (PLN)
    # the identity short-circuit must prevent http hits.
    assert hits == []
    assert series.base_currency == "PLN"


# ---------------------------------------------------------------------------
# soft delete / deactivation
# ---------------------------------------------------------------------------
def test_soft_deleted_planned_excluded(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.soft_delete(conn, USER_ID, world["p1"])
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 10, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 24)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 10, 25)), world["a1"]).native_minor
    assert prev == curr  # no drop


def test_deactivated_rule_excluded(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    recurring.deactivate_rule(conn, USER_ID, world["rule"])
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 31)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 1)), world["a1"]).native_minor
    assert prev == curr


def test_skipped_override_removes_occurrence(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=world["rule"],
            occurrence_date=date(2026, 11, 1),
            state=OverrideState.SKIPPED,
        ),
    )
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 31)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 1)), world["a1"]).native_minor
    assert prev == curr


# ---------------------------------------------------------------------------
# invariants
# ---------------------------------------------------------------------------
def test_deterministic_output(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    with _dead_client() as http:
        s1 = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    with _dead_client() as http:
        s2 = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    assert s1 == s2


def test_no_events_account_is_flat_line(conn: sqlite3.Connection) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Idle", currency="PLN", opening_balance=42_000))
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 15, "PLN")
    acct_id = series.days[0].by_account[0].account_id
    values = {_point_for(d, acct_id).native_minor for d in series.days}
    assert values == {42_000}


def test_difference_equals_signed_event_sum(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 30, "PLN")
    # (d1, d2] = (Oct 24, Nov 15]: expense -10_000 on Oct 25, transit -20_000 Nov 5,
    # recurring rent -300_000 Nov 1, income +800_000 Nov 15.
    d1 = _point_for(_day_for(series, date(2026, 10, 24)), world["a1"]).native_minor
    d2 = _point_for(_day_for(series, date(2026, 11, 15)), world["a1"]).native_minor
    assert d2 - d1 == -10_000 - 20_000 - 300_000 + 800_000


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------
def test_negative_horizon_raises(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    with _dead_client() as http, pytest.raises(ValueError, match="horizon_days"):
        forecast_svc.forecast(conn, USER_ID, http, TODAY, -1, "PLN")


def test_empty_db_returns_zero_filled_series(conn: sqlite3.Connection) -> None:
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 3, "PLN")
    assert len(series.days) == 4
    assert all(d.totals_base_minor == 0 for d in series.days)
    assert all(d.by_account == () for d in series.days)


def test_rule_outside_window_skipped(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    # Add a rule that starts well after the horizon; it must not emit events.
    recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2030, 1, 1),
            category_id=world["rent"],
            account_id=world["a1"],
            default_amount=999_999,
            default_description="far-future",
        ),
    )
    # Also an already-ended rule.
    recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2020, 1, 1),
            end_date=date(2020, 6, 1),
            category_id=world["rent"],
            account_id=world["a1"],
            default_amount=999_999,
            default_description="ancient",
        ),
    )
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 60, "PLN")
    # Original rent rule still fires on 2026-11-01.
    prev = _point_for(_day_for(series, date(2026, 10, 31)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 11, 1)), world["a1"]).native_minor
    assert prev - curr == 300_000  # only one rule contributed


def test_adjustment_planned_row_ignored(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    # Insert a planned row with adjustment direction (defensive path). The
    # forecast should ignore it silently per plan.
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 10, 26),
            category_id=world["reconciliation"],
            account_id=world["a1"],
            amount=42_000,
            description="defensive adjustment",
        ),
    )
    with _dead_client() as http:
        series = forecast_svc.forecast(conn, USER_ID, http, TODAY, 10, "PLN")
    prev = _point_for(_day_for(series, date(2026, 10, 25)), world["a1"]).native_minor
    curr = _point_for(_day_for(series, date(2026, 10, 26)), world["a1"]).native_minor
    # Only the Oct 25 groceries drop applied; adjustment ignored, so Oct 26 == Oct 25.
    assert prev == curr


# ---------------------------------------------------------------------------
# budget overlay (ADR-0042 / T-126)
# ---------------------------------------------------------------------------
def _primary_account_id(world_ids: dict[str, int]) -> int:
    return min(world_ids["a1"], world_ids["a2"], world_ids["a3"])


def test_overlay_off_matches_pre_overlay_projection(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Explicit opt-out reproduces the legacy planned+recurring projection."""
    _ = world
    # Even with a budget set, overlay disabled must leave the series unchanged.
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=dining, amount=60_000))
    with _dead_client() as http:
        off_a = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 30, "PLN", include_budget_overlay=False
        )
        off_b = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 30, "PLN", include_budget_overlay=False
        )
    assert off_a == off_b
    # Day-0 anchor + Oct 25 drop must match the pre-overlay invariants.
    day25 = _day_for(off_a, date(2026, 10, 25))
    day24 = _day_for(off_a, date(2026, 10, 24))
    a1 = world["a1"]
    assert _point_for(day24, a1).native_minor - _point_for(day25, a1).native_minor == 10_000


def test_overlay_spreads_unaccounted_budget_evenly_over_future_month(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Nov one-off budget with no spend/plans spreads 2_000/day on primary account."""
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    # Nov only; Oct + Dec resolve to None → zero overlay outside Nov.
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=dining, year=2026, month=11, amount=60_000),
    )
    a1 = world["a1"]
    assert _primary_account_id(world) == a1

    with _dead_client() as http:
        baseline = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 60, "PLN", include_budget_overlay=False
        )
        with_overlay = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 60, "PLN", include_budget_overlay=True
        )

    # Oct 23..31: no Nov overlay yet, no Oct budget → zero diff on A1.
    for d in (date(2026, 10, 23), date(2026, 10, 27), date(2026, 10, 31)):
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert over == base, f"unexpected overlay drift on {d}"

    # Nov cumulative drop = 2_000 * day_of_month.
    for day_of_month in (1, 15, 30):
        d = date(2026, 11, day_of_month)
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert base - over == 2_000 * day_of_month

    # Dec: no Dec budget → cumulative drop frozen at full 60_000 Nov overlay.
    for d in (date(2026, 12, 1), date(2026, 12, 22)):
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert base - over == 60_000


def test_overlay_clamps_when_planned_exceeds_budget(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Planned+recurring >= budget ⇒ overlay contributes nothing (no income flip)."""
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    # Budget 50_000; planned 60_000 in Nov on A2 (so overlay target A1 not pre-impacted).
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=dining, year=2026, month=11, amount=50_000),
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10),
            category_id=dining,
            account_id=world["a2"],
            amount=60_000,
            description="restaurants",
        ),
    )
    a1 = world["a1"]

    with _dead_client() as http:
        baseline = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 45, "PLN", include_budget_overlay=False
        )
        with_overlay = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 45, "PLN", include_budget_overlay=True
        )

    for d in (date(2026, 11, 1), date(2026, 11, 15), date(2026, 11, 30)):
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert base == over, f"overlay should be zero when committed>=budget ({d})"


def test_overlay_subtracts_spent_so_far_in_current_month(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Actual spend already in balance anchor must not be double-counted."""
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=dining, year=2026, month=10, amount=40_000),
    )
    # Actual Oct spend of 32_000 happened on Oct 15 (before TODAY=Oct 23). The
    # overlay should spread the residual 8_000 across the Oct 24..31 window.
    transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 10, 15),
            category_id=dining,
            account_id=world["a1"],
            amount=32_000,
            description="dining to-date",
        ),
    )
    a1 = world["a1"]
    with _dead_client() as http:
        baseline = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 20, "PLN", include_budget_overlay=False
        )
        with_overlay = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 20, "PLN", include_budget_overlay=True
        )
    # Oct 24..31 is 8 days; residual 8_000 → 1_000/day.
    for i, day_of_month in enumerate(range(24, 32), start=1):
        d = date(2026, 10, day_of_month)
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert base - over == 1_000 * i, f"day {d} unexpected diff"


def test_overlay_rounding_residual_absorbed_by_last_day(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Non-divisible unaccounted amount keeps the window sum exact."""
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    # 100 cents over 30 Nov days → ~3.33/day. ROUND_HALF_EVEN(3.33) = 3;
    # last-day residual = 100 - 3*29 = 100 - 87 = 13.
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=dining, year=2026, month=11, amount=100),
    )
    a1 = world["a1"]
    with _dead_client() as http:
        baseline = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 50, "PLN", include_budget_overlay=False
        )
        with_overlay = forecast_svc.forecast(
            conn, USER_ID, http, TODAY, 50, "PLN", include_budget_overlay=True
        )
    end_of_nov_baseline = _point_for(_day_for(baseline, date(2026, 11, 30)), a1).native_minor
    end_of_nov_overlay = _point_for(_day_for(with_overlay, date(2026, 11, 30)), a1).native_minor
    assert end_of_nov_baseline - end_of_nov_overlay == 100  # exact
    # Last Nov step applies the residual (13 cents vs 3 cents per prior day).
    nov29_overlay = _point_for(_day_for(with_overlay, date(2026, 11, 29)), a1).native_minor
    nov30_overlay = _point_for(_day_for(with_overlay, date(2026, 11, 30)), a1).native_minor
    assert nov29_overlay - nov30_overlay == 13


def test_overlay_deterministic_across_runs(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, USER_ID, NewBudgetDefault(category_id=dining, amount=90_000))
    with _dead_client() as http:
        a = forecast_svc.forecast(conn, USER_ID, http, TODAY, 60, "PLN")
        b = forecast_svc.forecast(conn, USER_ID, http, TODAY, 60, "PLN")
    assert a == b


def test_overlay_skipped_when_today_is_last_day_of_month(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Month-end ``today`` → event_start > month_end, overlay window empty for that month."""
    today = date(2026, 10, 31)
    # Cache FX for the new today so the EUR account converts.
    fx_repo.upsert_rate(
        conn,
        NewFxRate(date=today, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
    )
    dining = categories.create(
        conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
    ).id
    # Oct one-off would otherwise want to spread, but window is empty.
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=dining, year=2026, month=10, amount=99_000),
    )
    a1 = world["a1"]
    with _dead_client() as http:
        baseline = forecast_svc.forecast(
            conn, USER_ID, http, today, 15, "PLN", include_budget_overlay=False
        )
        with_overlay = forecast_svc.forecast(
            conn, USER_ID, http, today, 15, "PLN", include_budget_overlay=True
        )
    # Nov 1..15 falls into horizon; Nov has no budget → no overlay anywhere.
    for d in (today, date(2026, 11, 1), date(2026, 11, 15)):
        base = _point_for(_day_for(baseline, d), a1).native_minor
        over = _point_for(_day_for(with_overlay, d), a1).native_minor
        assert base == over, f"unexpected overlay on {d}"
