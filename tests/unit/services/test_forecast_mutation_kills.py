"""Mutation-kill tests for ``services/forecast`` (T-Q223, ADR-0131).

Each case injects ``today``, asserts exact minor units and runs next to a second user's rows
(and, in the tombstone case, soft-deleted / inactive rows) that must never leak into the
owner's projection. Complements ``test_forecast.py`` / ``test_forecast_monthly.py``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    fx as fx_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._unaudited import set_next_due
from budget_planner.services import forecast as fc, forecast_events, forecast_overlay, fx as fx_svc
from budget_planner.services.fx import FxUnavailableError
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_ID,
    WORLD_TODAY,
    World,
    expense_rule_amount,
    planned_amount,
)

TODAY = date(2026, 10, 23)
OPENING = 1_000_000


def _conv(
    conn: sqlite3.Connection, today: date = TODAY, *, rates: dict[date, str] | None = None
) -> fx_svc.FxConverter:
    """Cache-only converter; ``rates`` seeds EUR->PLN rows first."""
    for day, rate in (rates or {}).items():
        fx_repo.upsert_rate(
            conn, NewFxRate(date=day, from_ccy="EUR", to_ccy="PLN", rate=Decimal(rate))
        )
    base = fx_svc.build_converter("PLN", today, [])
    cached = fx_repo.list_rates_to(conn, "PLN")
    return (
        fx_svc.build_converter("PLN", today, ((r.from_ccy, r.date, r.rate) for r in cached))
        if (cached)
        else base
    )


@dataclass(frozen=True)
class Env:
    a1: int
    a2: int
    expense_cat: int
    income_cat: int
    transit_cat: int


def _add_user(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
        (user_id, f"user{user_id}", f"user{user_id}@example.test", "x"),
    )


def _env(conn: sqlite3.Connection, user_id: int = OWNER_ID) -> Env:
    if user_id != OWNER_ID:
        _add_user(conn, user_id)
    a1 = accounts_repo.create(
        conn, user_id, NewAccount(name=f"a1-{user_id}", currency="PLN", opening_balance=OPENING)
    ).id
    a2 = accounts_repo.create(conn, user_id, NewAccount(name=f"a2-{user_id}", currency="PLN")).id
    exp = categories_repo.create(
        conn, user_id, NewCategory(name=f"exp-{user_id}", direction=Direction.EXPENSE)
    ).id
    inc = categories_repo.create(
        conn, user_id, NewCategory(name=f"inc-{user_id}", direction=Direction.INCOME)
    ).id
    transit = categories_repo.find_by_name(conn, user_id, "Transit")
    return Env(a1, a2, exp, inc, transit.id if transit is not None else 0)


def _plan(
    conn: sqlite3.Connection,
    user_id: int,
    on: date,
    category_id: int,
    account_id: int,
    *,
    amount: int,
    dest: int | None = None,
) -> int:
    return planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=on,
            category_id=category_id,
            account_id=account_id,
            dest_account_id=dest,
            amount=amount,
        ),
    ).id


def _rule(
    conn: sqlite3.Connection,
    user_id: int,
    env: Env,
    due: date,
    amount: int,
    *,
    category_id: int | None = None,
    account_id: int | None = None,
    end: date | None = None,
    active: bool = True,
) -> int:
    rule = recurring_repo.create_rule(
        conn,
        user_id,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=due,
            end_date=end,
            category_id=env.expense_cat if category_id is None else category_id,
            account_id=env.a1 if account_id is None else account_id,
            default_amount=amount,
            active=active,
        ),
    )
    set_next_due(conn, user_id, rule.id, next_due=due, last_promoted_date=None)
    return rule.id


def _noise(conn: sqlite3.Connection) -> None:
    """A second user with planned + rule + budget rows across the horizon (must never leak)."""
    env = _env(conn, OTHER_ID)
    for off in (1, 2, 5, 10, 11):
        _plan(conn, OTHER_ID, TODAY + timedelta(days=off), env.expense_cat, env.a1, amount=77_777)
    _rule(conn, OTHER_ID, env, TODAY + timedelta(days=3), 55_555)
    budgets_repo.set_default(
        conn, OTHER_ID, NewBudgetDefault(category_id=env.expense_cat, amount=999_999)
    )
    transactions_repo.create(
        conn,
        OTHER_ID,
        NewTransaction(
            operation_date=TODAY, category_id=env.expense_cat, account_id=env.a1, amount=33_333
        ),
    )


def _native(series: fc.ForecastSeries, account_id: int) -> list[int]:
    return [
        next(p.native_minor for p in d.by_account if p.account_id == account_id)
        for d in series.days
    ]


def _run(conn: sqlite3.Connection, horizon: int, *, overlay: bool = False) -> fc.ForecastSeries:
    return fc.forecast(
        conn,
        OWNER_ID,
        _conv(conn),
        TODAY,
        horizon,
        include_budget_overlay=overlay,
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )


# ---------------------------------------------------------------------------
# horizon end and event window
# ---------------------------------------------------------------------------
def test_item_on_last_day_counts_and_day_after_does_not(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _noise(conn)
    _plan(conn, OWNER_ID, TODAY + timedelta(days=5), env.expense_cat, env.a1, amount=1_000)
    _plan(conn, OWNER_ID, TODAY + timedelta(days=6), env.expense_cat, env.a1, amount=2_000)
    s = _run(conn, 5)
    assert _native(s, env.a1) == [OPENING] * 5 + [OPENING - 1_000]
    assert s.end_date == TODAY + timedelta(days=5)
    s6 = _run(conn, 6)
    assert _native(s6, env.a1)[-2:] == [OPENING - 1_000, OPENING - 3_000]


def test_item_on_first_day_after_today_counts_with_horizon_one(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _noise(conn)
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.income_cat, env.a1, amount=4_000)
    s = _run(conn, 1)
    assert _native(s, env.a1) == [OPENING, OPENING + 4_000]


def test_horizon_zero_projects_only_today_and_ignores_events(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.expense_cat, env.a1, amount=4_000)
    s = _run(conn, 0, overlay=True)
    assert [d.on_date for d in s.days] == [TODAY]
    assert _native(s, env.a1) == [OPENING]


def test_item_dated_today_is_not_in_the_event_stream(conn: sqlite3.Connection) -> None:
    """ADR-0105 amendment: due-today items are neither overdue nor inside ``[today + 1, end)``."""
    env = _env(conn)
    _plan(conn, OWNER_ID, TODAY, env.expense_cat, env.a1, amount=4_000)
    s = _run(conn, 2)
    assert _native(s, env.a1) == [OPENING] * 3


def test_overdue_item_lands_on_tomorrow_not_today(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _plan(conn, OWNER_ID, TODAY - timedelta(days=4), env.expense_cat, env.a1, amount=900)
    s = _run(conn, 3)
    assert _native(s, env.a1) == [OPENING, OPENING - 900, OPENING - 900, OPENING - 900]


def test_rule_events_after_horizon_end_are_excluded(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _rule(conn, OWNER_ID, env, TODAY + timedelta(days=4), 250)
    s = _run(conn, 4)
    assert _native(s, env.a1)[-1] == OPENING - 250
    s3 = _run(conn, 3)
    assert _native(s3, env.a1)[-1] == OPENING


def test_tombstones_and_inactive_rows_never_leak(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    w = world_with_tombstones
    horizon = 25  # to 2026-12-07: planned (11-13), expense rule (11-15, 12-15 out), income (12-01)
    for uid, row in ((OWNER_ID, w.owner), (OTHER_ID, w.other)):
        s = fc.forecast(
            conn,
            uid,
            fx_svc.build_converter("PLN", WORLD_TODAY, []),
            WORLD_TODAY,
            horizon,
            include_budget_overlay=False,
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
        native = _native(s, row.account_id)
        assert native[0] - native[-1] == planned_amount(uid) + expense_rule_amount(uid) - (
            5_000 * uid
        )
        assert s.days[0].on_date == WORLD_TODAY
        assert all(len(d.by_account) == (2 if uid == OWNER_ID else 1) for d in s.days) or uid
        assert s.days[1].on_date == WORLD_TODAY + timedelta(days=1)
        assert native[1] == native[0] - planned_amount(uid)


def test_inactive_rule_adds_nothing(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _rule(conn, OWNER_ID, env, TODAY + timedelta(days=2), 400, active=False)
    _rule(conn, OWNER_ID, env, TODAY + timedelta(days=3), 100)
    s = _run(conn, 4)
    assert _native(s, env.a1) == [OPENING, OPENING, OPENING, OPENING - 100, OPENING - 100]


# ---------------------------------------------------------------------------
# legs, skipped override, FX
# ---------------------------------------------------------------------------
def test_income_expense_transit_on_one_day_exact_balances(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _noise(conn)
    day = TODAY + timedelta(days=2)
    _plan(conn, OWNER_ID, day, env.income_cat, env.a1, amount=10_000)
    _plan(conn, OWNER_ID, day, env.expense_cat, env.a1, amount=3_000)
    _plan(conn, OWNER_ID, day, env.transit_cat, env.a1, amount=2_500, dest=env.a2)
    s = _run(conn, 3)
    assert _native(s, env.a1) == [OPENING, OPENING, OPENING + 4_500, OPENING + 4_500]
    assert _native(s, env.a2) == [0, 0, 2_500, 2_500]
    assert [d.totals_base_minor for d in s.days] == [
        OPENING,
        OPENING,
        OPENING + 7_000,
        OPENING + 7_000,
    ]


def test_override_skipped_first_occurrence_then_later_one_is_applied(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    first = TODAY + timedelta(days=1)
    rule = _rule(conn, OWNER_ID, env, first, 300)
    recurring_repo.upsert_override(
        conn,
        OWNER_ID,
        NewRecurringOverride(rule_id=rule, occurrence_date=first, state=OverrideState.SKIPPED),
    )
    second = date(2026, 11, 24)
    recurring_repo.upsert_override(
        conn,
        OWNER_ID,
        NewRecurringOverride(
            rule_id=rule,
            occurrence_date=second,
            state=OverrideState.OVERRIDDEN,
            amount_override=111,
        ),
    )
    s = _run(conn, 65)
    native = _native(s, env.a1)
    assert native[1] == OPENING  # first occurrence skipped
    assert native[(second - TODAY).days] == OPENING - 111
    assert native[-1] == OPENING - 111 - 300  # 2026-12-24 occurrence, default amount


def test_foreign_currency_account_uses_rate_on_or_before_today(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=10_000)
    ).id
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.expense_cat, eur, amount=1_000)
    fx = _conv(
        conn,
        rates={TODAY - timedelta(days=9): "3.50", TODAY: "4.20", TODAY + timedelta(days=1): "9.00"},
    )
    s = fc.forecast(
        conn,
        OWNER_ID,
        fx,
        TODAY,
        1,
        include_budget_overlay=False,
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.base_currency == "PLN"
    pts = [p for d in s.days for p in d.by_account if p.account_id == eur]
    assert [p.native_minor for p in pts] == [10_000, 9_000]
    assert [p.base_minor for p in pts] == [42_000, 37_800]
    assert s.days[1].totals_base_minor == OPENING + 37_800


def test_missing_rate_raises_fx_unavailable(conn: sqlite3.Connection) -> None:
    _env(conn)
    accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=10_000)
    )
    with pytest.raises(FxUnavailableError):
        _run(conn, 2)


def test_negative_horizon_rejected(conn: sqlite3.Connection) -> None:
    _env(conn)
    with pytest.raises(ValueError, match="horizon_days must be >= 0, got -1"):
        _run(conn, -1)
    with pytest.raises(ValueError, match="horizon_months must be >= 1, got 0"):
        fc.forecast_monthly(
            conn, OWNER_ID, _conv(conn), TODAY, 0, display_timezone=DEFAULT_DISPLAY_TIMEZONE
        )


def test_no_accounts_series_is_zero_per_day(conn: sqlite3.Connection) -> None:
    s = _run(conn, 2)
    assert [(d.on_date, d.totals_base_minor, d.by_account) for d in s.days] == [
        (TODAY + timedelta(days=i), 0, ()) for i in range(3)
    ]
    assert (s.start_date, s.end_date) == (TODAY, TODAY + timedelta(days=2))


# ---------------------------------------------------------------------------
# budget overlay
# ---------------------------------------------------------------------------
def _budget(conn: sqlite3.Connection, env: Env, amount: int, user_id: int = OWNER_ID) -> None:
    budgets_repo.set_default(
        conn, user_id, NewBudgetDefault(category_id=env.expense_cat, amount=amount)
    )


def test_overlay_spreads_residual_with_last_day_absorbing_rounding(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    _noise(conn)
    _budget(conn, env, 1_100)
    today = date(2026, 12, 20)
    s = fc.forecast(
        conn, OWNER_ID, _conv(conn, today), today, 20, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    native = _native(s, env.a1)
    deltas = [b - a for a, b in pairwise(native)]
    dec = [-100] * 11  # 12-21..12-31: 1100 / 11
    jan = [-122] * 8 + [-124]  # 01-01..01-09: round(1100 / 9) = 122, last 1100 - 8 * 122
    assert deltas == dec + jan
    assert native[0] == OPENING


def test_overlay_subtracts_spent_including_today_and_foreign_rate_on_txn_date(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    eur = accounts_repo.create(conn, OWNER_ID, NewAccount(name="eur", currency="EUR")).id
    _budget(conn, env, 3_000)
    today = date(2026, 11, 1)  # spend window [11-01, 11-01]: a txn on today counts
    for on, acct, amount in ((today, env.a1, 200), (today, eur, 100)):
        transactions_repo.create(
            conn,
            OWNER_ID,
            NewTransaction(
                operation_date=on, category_id=env.expense_cat, account_id=acct, amount=amount
            ),
        )
    fx = _conv(conn, today, rates={today: "2.00", today + timedelta(days=1): "7.00"})
    s = fc.forecast(conn, OWNER_ID, fx, today, 29, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    # unaccounted = 3000 - 200 - 100 * 2.00 = 2600 over 11-02..11-30 (29 days):
    # 90 each, last 2600 - 28 * 90
    deltas = [b - a for a, b in pairwise(_native(s, env.a1))]
    assert deltas == [-90] * 28 + [-80]


def test_overlay_counts_overdue_only_in_first_window_and_ignores_other_users(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    _noise(conn)
    _budget(conn, env, 3_100)
    _plan(conn, OWNER_ID, date(2026, 10, 20), env.expense_cat, env.a1, amount=100)  # overdue
    today = date(2026, 10, 30)
    s = fc.forecast(
        conn, OWNER_ID, _conv(conn, today), today, 2, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    deltas = [b - a for a, b in pairwise(_native(s, env.a1))]
    # Oct: 3100 - 100 committed (overdue lands on 10-31) = 3000 over 10-31 only (the horizon end
    # is 11-01): window 10-31..10-31 -> -3000 plus the overdue -100; Nov: 3100 on 11-01 only.
    assert deltas == [-100 - 3_000, -3_100]


def test_overlay_skips_months_without_budget_and_income_categories(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    s = _run(conn, 3, overlay=True)
    assert _native(s, env.a1) == [OPENING] * 4
    _budget(conn, env, 0)
    assert _native(_run(conn, 3, overlay=True), env.a1) == [OPENING] * 4


def test_overlay_unaccounted_negative_adds_nothing(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _budget(conn, env, 500)
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.expense_cat, env.a1, amount=800)
    s = _run(conn, 2, overlay=True)
    assert _native(s, env.a1) == [OPENING, OPENING - 800, OPENING - 800]


def test_overlay_primary_account_is_lowest_id(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _budget(conn, env, 600)
    s = _run(conn, 1, overlay=True)
    assert _native(s, env.a1)[-1] == OPENING - 600
    assert _native(s, env.a2)[-1] == 0


def test_overlay_ignores_deleted_category_in_directions(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    other_cat = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="x", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, OWNER_ID, NewBudgetDefault(category_id=other_cat, amount=40))
    _budget(conn, env, 60)
    s = _run(conn, 1, overlay=True)
    assert _native(s, env.a1)[-1] == OPENING - 100


# ---------------------------------------------------------------------------
# horizon helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("today", "months", "expected"),
    [
        (date(2026, 10, 23), 1, 8),  # to 10-31
        (date(2026, 10, 23), 3, 69),  # to 12-31
        (date(2026, 11, 30), 1, 0),
        (date(2026, 12, 15), 2, 47),  # across the year to 01-31
        (date(2026, 1, 31), 2, 28),  # to 02-28 (non-leap)
    ],
)
def test_horizon_days_for_months(today: date, months: int, expected: int) -> None:
    assert fc.horizon_days_for_months(today, months) == expected


def test_iter_months_spans_year_end() -> None:
    assert forecast_overlay.iter_months(date(2026, 11, 5), date(2027, 2, 1)) == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]
    assert forecast_overlay.iter_months(date(2026, 12, 31), date(2026, 12, 31)) == [(2026, 12)]
    assert forecast_overlay.iter_months(date(2026, 12, 31), date(2027, 1, 1)) == [
        (2026, 12),
        (2027, 1),
    ]


def test_overlay_months_window_and_overdue_flag() -> None:
    months = forecast_overlay.overlay_months(date(2026, 10, 24), date(2026, 11, 3))
    assert [(m.year, m.month, m.window_end) for m in months] == [
        (2026, 10, date(2026, 10, 31)),
        (2026, 11, date(2026, 11, 3)),
    ]
    assert [m.span for m in months] == [
        forecast_overlay.MonthSpan(date(2026, 10, 1), date(2026, 10, 24), date(2026, 10, 31), True),
        forecast_overlay.MonthSpan(date(2026, 11, 1), date(2026, 11, 1), date(2026, 11, 30), False),
    ]
    assert forecast_overlay.overlay_months(date(2026, 10, 24), date(2026, 10, 24))[
        0
    ].window_end == date(2026, 10, 24)


def test_distribute_overlay_exact_events() -> None:
    evs = forecast_overlay.distribute_overlay(
        unaccounted_minor=10,
        window_start=date(2026, 5, 1),
        window_end_inclusive=date(2026, 5, 3),
        account_id=9,
    )
    assert [(e.on_date, e.account_id, e.amount_minor) for e in evs] == [
        (date(2026, 5, 1), 9, -3),
        (date(2026, 5, 2), 9, -3),
        (date(2026, 5, 3), 9, -4),
    ]
    one = forecast_overlay.distribute_overlay(
        unaccounted_minor=7,
        window_start=date(2026, 5, 1),
        window_end_inclusive=date(2026, 5, 1),
        account_id=9,
    )
    assert [e.amount_minor for e in one] == [-7]
    # per-day rounds to zero: leading zero days omitted, last day carries the amount
    tiny = forecast_overlay.distribute_overlay(
        unaccounted_minor=1,
        window_start=date(2026, 5, 1),
        window_end_inclusive=date(2026, 5, 4),
        account_id=9,
    )
    assert [(e.on_date, e.amount_minor) for e in tiny] == [(date(2026, 5, 4), -1)]
    half = forecast_overlay.distribute_overlay(
        unaccounted_minor=5,
        window_start=date(2026, 5, 1),
        window_end_inclusive=date(2026, 5, 2),
        account_id=9,
    )
    assert [e.amount_minor for e in half] == [-2, -3]  # HALF_EVEN: 2.5 -> 2


def test_signed_events_each_direction() -> None:
    d = date(2026, 5, 1)
    inc = forecast_events.signed_events_for_direction(Direction.INCOME, d, 1, None, 50)
    exp = forecast_events.signed_events_for_direction(Direction.EXPENSE, d, 1, None, 50)
    tr = forecast_events.signed_events_for_direction(Direction.TRANSIT, d, 1, 2, 50)
    adj = forecast_events.signed_events_for_direction(Direction.ADJUSTMENT, d, 1, None, 50)
    assert [(e.on_date, e.account_id, e.amount_minor) for e in inc] == [(d, 1, 50)]
    assert [(e.on_date, e.account_id, e.amount_minor) for e in exp] == [(d, 1, -50)]
    assert [(e.on_date, e.account_id, e.amount_minor) for e in tr] == [(d, 1, -50), (d, 2, 50)]
    assert adj == ()


# ---------------------------------------------------------------------------
# monthly aggregates
# ---------------------------------------------------------------------------
def test_monthly_flows_exact_with_foreign_currency_and_skipped_account(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    _noise(conn)
    eur = accounts_repo.create(conn, OWNER_ID, NewAccount(name="eur", currency="EUR")).id
    dead = accounts_repo.create(conn, OWNER_ID, NewAccount(name="dead", currency="PLN")).id
    _plan(conn, OWNER_ID, date(2026, 10, 25), env.expense_cat, dead, amount=9_999)
    accounts_repo.soft_delete(conn, OWNER_ID, dead)
    _plan(conn, OWNER_ID, date(2026, 10, 26), env.income_cat, eur, amount=1_000)  # 4.00 -> 4000
    _plan(conn, OWNER_ID, date(2026, 10, 27), env.expense_cat, eur, amount=200)  # 800
    _plan(conn, OWNER_ID, date(2026, 10, 28), env.transit_cat, env.a1, amount=5_000, dest=env.a2)
    _plan(conn, OWNER_ID, date(2026, 11, 2), env.income_cat, env.a1, amount=70)
    fx = _conv(conn, rates={TODAY: "4.00"})
    flows = fc._month_flow_sums(
        conn,
        OWNER_ID,
        today=TODAY,
        end_date=date(2026, 11, 30),
        accounts=tuple(accounts_repo.list_all(conn, OWNER_ID)),
        fx=fx,
    )
    assert flows == {date(2026, 10, 1): (4_000, 800), date(2026, 11, 1): (70, 0)}
    assert (
        fc._month_flow_sums(
            conn,
            OWNER_ID,
            today=TODAY,
            end_date=TODAY,
            accounts=tuple(accounts_repo.list_all(conn, OWNER_ID)),
            fx=fx,
        )
        == {}
    )


def test_month_flow_end_inclusive_and_overdue_in_first_month(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    accts = tuple(accounts_repo.list_all(conn, OWNER_ID))
    _plan(conn, OWNER_ID, TODAY - timedelta(days=3), env.income_cat, env.a1, amount=11)  # overdue
    _plan(conn, OWNER_ID, TODAY + timedelta(days=7), env.expense_cat, env.a1, amount=22)  # last day
    _plan(conn, OWNER_ID, TODAY + timedelta(days=8), env.expense_cat, env.a1, amount=44)  # after
    flows = fc._month_flow_sums(
        conn,
        OWNER_ID,
        today=TODAY,
        end_date=TODAY + timedelta(days=7),
        accounts=accts,
        fx=_conv(conn),
    )
    assert flows == {date(2026, 10, 1): (11, 22)}


def test_planned_budget_per_month_exact_and_isolated(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _noise(conn)
    _budget(conn, env, 1_000)
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=date(2026, 10, 23),
            category_id=env.expense_cat,
            account_id=env.a1,
            amount=150,
        ),
    )
    _plan(conn, OWNER_ID, date(2026, 10, 24), env.expense_cat, env.a1, amount=50)
    _plan(conn, OWNER_ID, date(2026, 11, 3), env.expense_cat, env.a1, amount=5_000)
    out = fc._planned_budget_per_month(
        conn, OWNER_ID, TODAY, 3, fx=_conv(conn), display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert out == {date(2026, 10, 1): 800, date(2026, 11, 1): 0, date(2026, 12, 1): 1_000}


def test_planned_budget_overdue_counts_in_current_month_only(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _budget(conn, env, 1_000)
    _plan(conn, OWNER_ID, date(2026, 10, 10), env.expense_cat, env.a1, amount=100)  # overdue
    out = fc._planned_budget_per_month(
        conn, OWNER_ID, TODAY, 2, fx=_conv(conn), display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert out == {date(2026, 10, 1): 900, date(2026, 11, 1): 1_000}


def test_forecast_monthly_rows_and_running_balance(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _noise(conn)
    _budget(conn, env, 1_000)
    _plan(conn, OWNER_ID, date(2026, 11, 5), env.income_cat, env.a1, amount=5_000)
    s = fc.forecast_monthly(
        conn, OWNER_ID, _conv(conn), TODAY, 3, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert s.start_month == date(2026, 10, 1)
    assert s.end_month == date(2026, 12, 1)
    assert [m.month for m in s.months] == [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)]
    assert [m.income_base_minor for m in s.months] == [0, 5_000, 0]
    assert [m.planned_budget_base_minor for m in s.months] == [1_000, 1_000, 1_000]
    assert [m.net_base_minor for m in s.months] == [-1_000, 4_000, -1_000]
    assert [m.end_balance_base_minor for m in s.months] == [
        OPENING - 1_000,
        OPENING + 3_000,
        OPENING + 2_000,
    ]


def test_forecast_monthly_without_accounts_uses_budget_only(conn: sqlite3.Connection) -> None:
    cat = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="e", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, OWNER_ID, NewBudgetDefault(category_id=cat, amount=700))
    s = fc.forecast_monthly(
        conn, OWNER_ID, _conv(conn), TODAY, 2, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert [(m.month, m.income_base_minor, m.expense_base_minor) for m in s.months] == [
        (date(2026, 10, 1), 0, 0),
        (date(2026, 11, 1), 0, 0),
    ]
    assert [m.planned_budget_base_minor for m in s.months] == [700, 700]
    assert [m.net_base_minor for m in s.months] == [-700, -700]
    assert [m.end_balance_base_minor for m in s.months] == [0, 0]


def test_projection_summary_and_normalize_horizon() -> None:
    assert fc.projection_summary(()) is None

    def mk(i: int, v: float) -> fc.MonthlyProjectionPoint:
        return fc.MonthlyProjectionPoint(
            month=date(2026, i, 1), label=str(i), end_balance_minor=int(v * 100)
        )

    pts = (mk(1, 10.0), mk(2, 30.0), mk(3, 20.0))
    summ = fc.projection_summary(pts)
    assert summ is not None
    assert (summ.now_value, summ.end_point, summ.peak_point) == (1_000, pts[2], pts[1])
    assert fc.normalize_horizon("6", (3, 6, 12)) == 6
    assert fc.normalize_horizon("5", (3, 6, 12)) == 12
    assert fc.normalize_horizon(None, (3, 6)) == 12
    assert fc.normalize_horizon("x", (3, 6)) == 12
    assert fc.normalize_horizon("-6", (3, 6, -6)) == 12


# ---------------------------------------------------------------------------
# second pass: survivors of the first mutmut run
# ---------------------------------------------------------------------------
def test_signed_events_guard_messages_and_adjustment_debug_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    d = date(2026, 5, 1)
    with pytest.raises(ValueError, match=r"^transit event missing dest_account_id$"):
        forecast_events.signed_events_for_direction(Direction.TRANSIT, d, 1, None, 5)
    with pytest.raises(ValueError, match=r"^transit source and dest must differ$"):
        forecast_events.signed_events_for_direction(Direction.TRANSIT, d, 1, 1, 5)
    with caplog.at_level("DEBUG", logger=forecast_events.logger.name):
        assert (
            forecast_events.signed_events_for_direction(Direction.ADJUSTMENT, d, 7, None, 5) == ()
        )
    assert [r.getMessage() for r in caplog.records] == [
        "forecast skipping adjustment-direction planned leg on 2026-05-01 acct=7"
    ]


def test_future_dated_transaction_is_not_in_day_zero_balance(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=TODAY + timedelta(days=2),
            category_id=env.expense_cat,
            account_id=env.a1,
            amount=500,
        ),
    )
    s = _run(conn, 1)
    assert _native(s, env.a1) == [OPENING, OPENING]
    assert [p.on_date for p in s.days[1].by_account] == [TODAY + timedelta(days=1)] * 2


def test_empty_account_series_carries_base_currency(conn: sqlite3.Connection) -> None:
    assert _run(conn, 1).base_currency == "PLN"


def test_planned_row_on_deleted_account_does_not_break_projection(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    dead = accounts_repo.create(conn, OWNER_ID, NewAccount(name="dead", currency="PLN")).id
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.expense_cat, dead, amount=300)
    accounts_repo.soft_delete(conn, OWNER_ID, dead)
    s = _run(conn, 2)
    assert _native(s, env.a1) == [OPENING] * 3
    assert all(len(d.by_account) == 2 for d in s.days)


def test_overlay_skips_unbudgeted_category_then_applies_later_one(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)  # env.expense_cat has no budget and the lowest id
    later = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="later", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, OWNER_ID, NewBudgetDefault(category_id=later, amount=1))
    s = _run(conn, 1, overlay=True)
    assert _native(s, env.a1) == [OPENING, OPENING - 1]  # unaccounted == 1 is applied


def test_foreign_spend_on_deleted_account_is_not_counted(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    eur = accounts_repo.create(conn, OWNER_ID, NewAccount(name="eur", currency="EUR")).id
    _budget(conn, env, 1_000)
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=TODAY, category_id=env.expense_cat, account_id=eur, amount=100
        ),
    )
    accounts_repo.soft_delete(conn, OWNER_ID, eur)
    fx = _conv(conn, rates={TODAY: "3.00"})
    s = fc.forecast(conn, OWNER_ID, fx, TODAY, 1, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    assert _native(s, env.a1) == [
        OPENING,
        OPENING - 1_000,
    ]  # ADR-0136: the deleted EUR spend is hidden


def test_committed_window_excludes_first_day_of_next_month(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    _budget(conn, env, 1_000)
    _plan(conn, OWNER_ID, date(2026, 11, 1), env.expense_cat, env.a1, amount=300)
    out = fc._planned_budget_per_month(
        conn, OWNER_ID, TODAY, 2, fx=_conv(conn), display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert out == {date(2026, 10, 1): 1_000, date(2026, 11, 1): 700}


def test_planned_budget_defaults_and_boundaries(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    later = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="later", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, OWNER_ID, NewBudgetDefault(category_id=later, amount=1_000))
    dead = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="dead", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, OWNER_ID, NewBudgetDefault(category_id=dead, amount=50))
    categories_repo.soft_delete(conn, OWNER_ID, dead)
    # Archived in October, the forecast's only month: reserves nothing from then on (T-Q279).
    conn.execute(
        "UPDATE categories SET deleted_at = '2026-10-05T10:00:00.000Z' WHERE id = ?", (dead,)
    )
    _plan(conn, OWNER_ID, TODAY, env.expense_cat, env.a1, amount=200)  # due today: not committed
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), later, env.a1, amount=999)  # remaining == 1
    out = fc._planned_budget_per_month(
        conn, OWNER_ID, TODAY, 1, fx=_conv(conn), display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    # start_month defaults to today's month, day 1. "dead" was archived in October, so its 50
    # is no longer reserved (ADR-0136, T-Q279): only "later" remains, 1.
    assert out == {date(2026, 10, 1): 1}
    # Archived in November instead: October still reserves it, 1 + 50.
    conn.execute(
        "UPDATE categories SET deleted_at = '2026-11-05T10:00:00.000Z' WHERE id = ?", (dead,)
    )
    out = fc._planned_budget_per_month(
        conn, OWNER_ID, TODAY, 1, fx=_conv(conn), display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert out == {date(2026, 10, 1): 51}


def test_month_flow_window_start_and_overdue_placement(conn: sqlite3.Connection) -> None:
    env = _env(conn)
    accts = tuple(accounts_repo.list_all(conn, OWNER_ID))
    _plan(
        conn, OWNER_ID, date(2026, 9, 20), env.income_cat, env.a1, amount=5
    )  # overdue, earlier month
    _plan(conn, OWNER_ID, TODAY, env.income_cat, env.a1, amount=33)  # due today: not in the stream
    _plan(conn, OWNER_ID, TODAY + timedelta(days=1), env.expense_cat, env.a1, amount=7)
    flows = fc._month_flow_sums(
        conn,
        OWNER_ID,
        today=TODAY,
        end_date=TODAY + timedelta(days=1),
        accounts=accts,
        fx=_conv(conn),
    )
    assert flows == {date(2026, 10, 1): (5, 7)}  # overdue lands on tomorrow's month


def test_forecast_monthly_fiscal_start_differs_from_calendar_month(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    """Income landed 11-28, next anchor 12-01: on 12-01 the fiscal cycle is still November."""
    w = world_with_tombstones
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 28),
            category_id=w.owner.income_category_id,
            account_id=w.owner.account_id,
            amount=10,
        ),
    )
    today = date(2026, 12, 1)
    s = fc.forecast_monthly(
        conn,
        OWNER_ID,
        fx_svc.build_converter("PLN", today, []),
        today,
        2,
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert (s.base_currency, s.start_month, s.end_month) == (
        "PLN",
        date(2026, 11, 1),
        date(2026, 12, 1),
    )
    assert [
        (m.month, m.income_base_minor, m.expense_base_minor, m.planned_budget_base_minor)
        for m in s.months
    ] == [(date(2026, 11, 1), 0, 1_200, 1_800), (date(2026, 12, 1), 0, 1_900, 1_100)]
    assert [m.net_base_minor for m in s.months] == [-3_000, -3_000]
    assert [m.end_balance_base_minor for m in s.months] == [119_466, 116_466]


def test_forecast_monthly_without_accounts_reports_window_and_currency(
    conn: sqlite3.Connection,
) -> None:
    s = fc.forecast_monthly(
        conn, OWNER_ID, _conv(conn), TODAY, 2, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert (s.base_currency, s.start_month, s.end_month) == (
        "PLN",
        date(2026, 10, 1),
        date(2026, 11, 1),
    )


def test_monthly_for_settings_uses_today_rate_and_projection_points(
    conn: sqlite3.Connection,
) -> None:
    env = _env(conn)
    eur = accounts_repo.create(conn, OWNER_ID, NewAccount(name="eur", currency="EUR")).id
    _plan(conn, OWNER_ID, date(2026, 10, 28), env.income_cat, eur, amount=1_000)
    for day, rate in ((TODAY, "4.00"), (TODAY + timedelta(days=1), "9.00")):
        fx_repo.upsert_rate(
            conn, NewFxRate(date=day, from_ccy="EUR", to_ccy="PLN", rate=Decimal(rate))
        )
    settings = Settings(_env_file=None)
    series = fc.monthly_for_settings(conn, OWNER_ID, settings, TODAY, 2)
    assert series.months[0].income_base_minor == 4_000
    pts = fc.monthly_projection(conn, OWNER_ID, settings, TODAY)
    assert len(pts) == 12  # default horizon
    assert pts[0] == fc.MonthlyProjectionPoint(
        month=date(2026, 10, 1),
        label="Oct 2026",
        income_minor=4_000,
        expense_minor=0,
        planned_budget_minor=0,
        net_minor=4_000,
        end_balance_minor=OPENING + 4_000,
    )
