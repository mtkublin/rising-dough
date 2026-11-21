"""Canonical budget period windows (ADR-0138, amends ADR-0041/0064/0085).

Pure: no clock, no I/O. A budget period is a half-open ``[start, end)`` window.
Without an income anchor the window is the calendar month, so ``end`` is the
first day of the next month (never the inclusive last day).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

MONTHS_IN_YEAR = 12
_ONE_DAY = dt.timedelta(days=1)


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    """Half-open period ``[start, end)``."""

    start: dt.date
    end: dt.date

    @property
    def last_day(self) -> dt.date:
        """Return the last day inside the window (``end - 1 day``)."""
        return self.end - _ONE_DAY

    @property
    def length_days(self) -> int:
        """Return the number of days in the window."""
        return (self.end - self.start).days


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return ``(year, month)`` moved by ``delta`` months (negative = back)."""
    total = year * MONTHS_IN_YEAR + (month - 1) + delta
    return total // MONTHS_IN_YEAR, (total % MONTHS_IN_YEAR) + 1


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    """Return ``(first_day, last_day)`` of the calendar month, both inclusive."""
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def next_month_start(year: int, month: int) -> dt.date:
    """Return the first day of the month after ``(year, month)`` (exclusive month end)."""
    return dt.date(*shift_month(year, month, 1), 1)


def clamp_day(year: int, month: int, day: int) -> dt.date:
    """Return ``date(year, month, day)`` with ``day`` clamped to the month length."""
    return dt.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def fiscal_window(
    today: dt.date,
    *,
    period_start: dt.date | None = None,
    next_income: dt.date | None = None,
) -> PeriodWindow:
    """Return the period window containing ``today``.

    ``period_start`` defaults to the first of ``today``'s month and
    ``next_income`` (exclusive end) to the first of the next month.
    """
    start = period_start if period_start is not None else today.replace(day=1)
    end = next_income if next_income is not None else next_month_start(today.year, today.month)
    return PeriodWindow(start=start, end=end)


def days_remaining(today: dt.date, end: dt.date) -> int:
    """Return days left in the period counting ``today``; floored at 1 (degenerate input guard)."""
    return max((end - today).days, 1)


def window_label_month(window: PeriodWindow) -> tuple[int, int]:
    """Return the ``(year, month)`` holding most of the window's days (tie: later month)."""
    counts: dict[tuple[int, int], int] = {}
    day = window.start
    while day < window.end:
        key = (day.year, day.month)
        counts[key] = counts.get(key, 0) + 1
        day += _ONE_DAY
    if not counts:
        return window.start.year, window.start.month
    return max(counts, key=lambda ym: (counts[ym], ym))
