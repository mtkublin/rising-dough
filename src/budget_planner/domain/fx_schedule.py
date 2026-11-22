"""When the daily FX refresh runs (ADR-0145): pure wall-clock arithmetic.

The refresh is due once per local day from 12:30 in the display timezone (NBP
publishes around noon). Times are built from the local wall clock, so a DST
change moves the UTC instant but never the local 12:30.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Final

REFRESH_TIME: Final = time(12, 30)


def _refresh_instant(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, REFRESH_TIME, tzinfo=tz).astimezone(UTC)


def local_day(now: datetime, tz: tzinfo) -> date:
    """The calendar date of ``now`` in ``tz``."""
    return now.astimezone(tz).date()


def next_run_at(now: datetime, tz: tzinfo) -> datetime:
    """First 12:30 local time strictly after ``now``, as a UTC instant."""
    today_run = _refresh_instant(local_day(now, tz), tz)
    if today_run > now:
        return today_run
    return _refresh_instant(local_day(now, tz) + timedelta(days=1), tz)


def is_due(now: datetime, tz: tzinfo, last_ran_on: date | None) -> bool:
    """True from 12:30 local time on a day the refresh has not yet run."""
    day = local_day(now, tz)
    return last_ran_on != day and now >= _refresh_instant(day, tz)
