"""When the daily FX refresh runs (ADR-0145): pure wall-clock arithmetic.

The refresh is due once per local day from 12:30 in the display timezone (NBP
publishes around noon). A failed run is retried hourly until 18:00 local time;
a success or a "no data" answer ends the day's attempts (ADR-0145 amendment
2026-11-22). Times are built from the local wall clock, so a DST change moves
the UTC instant but never the local 12:30.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum
from typing import Final

REFRESH_TIME: Final = time(12, 30)
RETRY_INTERVAL: Final = timedelta(hours=1)
RETRY_CUTOFF: Final = time(18, 0)


class Outcome(StrEnum):
    """How the last attempt ended. ``OK`` includes "no data" (a holiday 404)."""

    OK = "ok"
    FAILED = "failed"


def _refresh_instant(day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, REFRESH_TIME, tzinfo=tz).astimezone(UTC)


def local_day(now: datetime, tz: tzinfo) -> date:
    """The calendar date of ``now`` in ``tz``."""
    return now.astimezone(tz).date()


def retry_at(last_attempt: datetime, tz: tzinfo) -> datetime | None:
    """When a failed ``last_attempt`` is retried, or ``None`` when its day is over.

    Only attempts made from 12:30 local on are retried (an earlier failed
    startup run waits for the 12:30 run); the retry is one hour later and must
    fall on the same local day at or before 18:00.
    """
    day = local_day(last_attempt, tz)
    if last_attempt < _refresh_instant(day, tz):
        return None
    candidate = last_attempt + RETRY_INTERVAL
    local = candidate.astimezone(tz)
    if local.date() != day or local.time() > RETRY_CUTOFF:
        return None
    return candidate


def next_run_at(
    now: datetime,
    tz: tzinfo,
    last_attempt: datetime | None = None,
    last_outcome: Outcome | None = None,
) -> datetime:
    """Next instant strictly after ``now`` at which the loop should check again.

    The first 12:30 local time after ``now``, or the pending retry of a failed
    ``last_attempt`` when that comes sooner.
    """
    today_run = _refresh_instant(local_day(now, tz), tz)
    scheduled = (
        today_run
        if today_run > now
        else _refresh_instant(local_day(now, tz) + timedelta(days=1), tz)
    )
    if last_attempt is not None and last_outcome is Outcome.FAILED:
        retry = retry_at(last_attempt, tz)
        if retry is not None and retry > now:
            return min(retry, scheduled)
    return scheduled


def is_due(
    now: datetime,
    tz: tzinfo,
    last_ran_on: date | None,
    last_attempt: datetime | None = None,
    last_outcome: Outcome | None = None,
) -> bool:
    """True when a run is due: from 12:30 local on a day not yet finished.

    ``last_ran_on`` is the local day a run ended (success or no data). After a
    failed attempt made from 12:30 on, the next run is the hourly retry
    (:func:`retry_at`) and none once it is past 18:00.
    """
    day = local_day(now, tz)
    run = _refresh_instant(day, tz)
    if last_ran_on == day or now < run:
        return False
    if last_attempt is not None and last_outcome is Outcome.FAILED and last_attempt >= run:
        retry = retry_at(last_attempt, tz)
        return retry is not None and now >= retry
    return True
