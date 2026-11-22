"""Daily FX refresh schedule: 12:30 Europe/Warsaw, exact across DST (T-Q290, ADR-0145)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from budget_planner.domain import fx_schedule

WARSAW = ZoneInfo("Europe/Warsaw")


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # CET (UTC+1): 12:30 local is 11:30Z
        (_utc(2026, 1, 15, 10, 0), _utc(2026, 1, 15, 11, 30)),
        (_utc(2026, 1, 15, 11, 30), _utc(2026, 1, 16, 11, 30)),
        (_utc(2026, 1, 15, 15, 0), _utc(2026, 1, 16, 11, 30)),
        # Spring forward 2026-03-29 (CEST, UTC+2): 12:30 local is 10:30Z
        (_utc(2026, 3, 28, 12, 0), _utc(2026, 3, 29, 10, 30)),
        (_utc(2026, 3, 29, 10, 29), _utc(2026, 3, 29, 10, 30)),
        # Fall back 2026-10-25 (CET again): 11:30Z
        (_utc(2026, 10, 24, 12, 0), _utc(2026, 10, 25, 11, 30)),
        (_utc(2026, 10, 25, 11, 30), _utc(2026, 10, 26, 11, 30)),
    ],
)
def test_next_run_at_is_local_1230_in_utc(now: datetime, expected: datetime) -> None:
    assert fx_schedule.next_run_at(now, WARSAW) == expected


def test_not_due_before_1230_local() -> None:
    assert not fx_schedule.is_due(_utc(2026, 1, 15, 11, 29), WARSAW, None)


def test_due_from_1230_local_once_per_day() -> None:
    now = _utc(2026, 1, 15, 11, 30)
    assert fx_schedule.is_due(now, WARSAW, None)
    assert fx_schedule.is_due(now, WARSAW, date(2026, 1, 14))
    assert not fx_schedule.is_due(now, WARSAW, date(2026, 1, 15))
    assert not fx_schedule.is_due(_utc(2026, 1, 15, 18, 0), WARSAW, date(2026, 1, 15))


def test_due_boundary_follows_dst() -> None:
    # 2026-03-29 is CEST: 10:29Z is 12:29 local (not due), 10:30Z is due.
    assert not fx_schedule.is_due(_utc(2026, 3, 29, 10, 29), WARSAW, None)
    assert fx_schedule.is_due(_utc(2026, 3, 29, 10, 30), WARSAW, None)


FAILED = fx_schedule.Outcome.FAILED


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        # CET: 12:30 local is 11:30Z; retries hourly, last one at 18:00 local (17:00Z)
        (_utc(2026, 1, 15, 11, 30), _utc(2026, 1, 15, 12, 30)),
        (_utc(2026, 1, 15, 16, 0), _utc(2026, 1, 15, 17, 0)),  # 17:00 -> 18:00 local, allowed
        (_utc(2026, 1, 15, 16, 30), None),  # 18:30 local is past the cutoff
        (_utc(2026, 1, 15, 10, 0), None),  # failed startup run before 12:30 local
        # CEST: 12:30 local is 10:30Z
        (_utc(2026, 7, 15, 10, 30), _utc(2026, 7, 15, 11, 30)),
        (_utc(2026, 7, 15, 15, 30), None),  # 17:30 local + 1 h = 18:30 local
        (_utc(2026, 7, 15, 15, 0), _utc(2026, 7, 15, 16, 0)),  # 18:00 local
    ],
)
def test_retry_at(attempt: datetime, expected: datetime | None) -> None:
    assert fx_schedule.retry_at(attempt, WARSAW) == expected


def test_next_run_after_failure_is_the_hourly_retry_then_next_day() -> None:
    attempt = _utc(2026, 1, 15, 11, 30)
    assert fx_schedule.next_run_at(attempt, WARSAW, attempt, FAILED) == _utc(2026, 1, 15, 12, 30)
    late = _utc(2026, 1, 15, 16, 30)
    assert fx_schedule.next_run_at(late, WARSAW, late, FAILED) == _utc(2026, 1, 16, 11, 30)
    ok = fx_schedule.Outcome.OK
    assert fx_schedule.next_run_at(attempt, WARSAW, attempt, ok) == _utc(2026, 1, 16, 11, 30)


def test_next_run_after_failure_across_dst_start() -> None:
    attempt = _utc(2026, 3, 29, 10, 30)  # 12:30 CEST on the spring-forward day
    assert fx_schedule.next_run_at(attempt, WARSAW, attempt, FAILED) == _utc(2026, 3, 29, 11, 30)


def test_is_due_follows_retry_window() -> None:
    attempt = _utc(2026, 1, 15, 11, 30)
    assert not fx_schedule.is_due(_utc(2026, 1, 15, 12, 29), WARSAW, None, attempt, FAILED)
    assert fx_schedule.is_due(_utc(2026, 1, 15, 12, 30), WARSAW, None, attempt, FAILED)
    late = _utc(2026, 1, 15, 16, 30)
    assert not fx_schedule.is_due(_utc(2026, 1, 15, 17, 30), WARSAW, None, late, FAILED)
    # next day: a fresh run, whatever yesterday's outcome was
    assert fx_schedule.is_due(_utc(2026, 1, 16, 11, 30), WARSAW, None, late, FAILED)
