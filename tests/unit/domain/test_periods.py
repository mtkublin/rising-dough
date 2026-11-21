"""Pure period helpers (ADR-0138)."""

from __future__ import annotations

from datetime import date

from budget_planner.domain.periods import (
    PeriodWindow,
    clamp_day,
    days_remaining,
    fiscal_window,
    month_bounds,
    next_month_start,
    shift_month,
    window_label_month,
)


def test_month_bounds_inclusive_last_day() -> None:
    assert month_bounds(2026, 2) == (date(2026, 2, 1), date(2026, 2, 28))
    assert month_bounds(2028, 2)[1] == date(2028, 2, 29)


def test_shift_month_rolls_years() -> None:
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)
    assert shift_month(2026, 7, 0) == (2026, 7)


def test_next_month_start_is_exclusive_month_end() -> None:
    assert next_month_start(2026, 11) == date(2026, 12, 1)
    assert next_month_start(2026, 12) == date(2027, 1, 1)


def test_clamp_day() -> None:
    assert clamp_day(2026, 2, 31) == date(2026, 2, 28)
    assert clamp_day(2026, 3, 30) == date(2026, 3, 30)


def test_fiscal_window_without_anchor_is_calendar_month_half_open() -> None:
    w = fiscal_window(date(2026, 11, 19))
    assert (w.start, w.end) == (date(2026, 11, 1), date(2026, 12, 1))
    assert w.last_day == date(2026, 11, 30)
    assert w.length_days == 30
    assert days_remaining(date(2026, 11, 19), w.end) == 12


def test_fiscal_window_with_anchor_dates() -> None:
    w = fiscal_window(
        date(2026, 11, 26), period_start=date(2026, 11, 25), next_income=date(2026, 12, 25)
    )
    assert (w.start, w.end) == (date(2026, 11, 25), date(2026, 12, 25))


def test_days_remaining_floor() -> None:
    assert days_remaining(date(2026, 11, 30), date(2026, 11, 30)) == 1
    assert days_remaining(date(2026, 12, 2), date(2026, 11, 30)) == 1


def test_label_month_most_days_wins() -> None:
    assert window_label_month(PeriodWindow(date(2026, 12, 2), date(2027, 1, 1))) == (2026, 12)
    assert window_label_month(PeriodWindow(date(2026, 11, 29), date(2026, 12, 28))) == (2026, 12)
    assert window_label_month(PeriodWindow(date(2026, 1, 25), date(2026, 2, 25))) == (2026, 2)


def test_label_month_tie_goes_to_later_month() -> None:
    # Feb 15 to Mar 15 (2026): 14 days in each month.
    assert window_label_month(PeriodWindow(date(2026, 2, 15), date(2026, 3, 15))) == (2026, 3)
