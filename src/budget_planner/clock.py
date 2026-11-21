"""The single source of "now" and "today" (ADR-0130 section 4, ADR-0007).

The ruff ``TID251`` ban on ``datetime.date.today``, ``datetime.datetime.now``,
``datetime.datetime.utcnow`` and ``time.time`` covers all of ``src/``;
``clock.py`` is the one module allowed to read the host clock (ADR-0140).

Rules (ADR-0007):

- Instants are timezone-aware UTC.
- "Today" is a naive ``date`` in the display timezone, never the host's.
- Tests pin time with :func:`frozen`, not by patching ``datetime``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """A source of timezone-aware instants."""

    def now(self) -> datetime: ...


class HasDisplayTimezone(Protocol):
    """Anything exposing the IANA display timezone (e.g. ``Settings``)."""

    @property
    def display_timezone(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FixedClock:
    """A clock that always returns the same instant (tests, replays)."""

    instant: datetime

    def now(self) -> datetime:
        return self.instant


@dataclass(frozen=True, slots=True)
class SystemClock:
    """The host clock, read as UTC. The only place the wall clock is touched."""

    def now(self) -> datetime:
        return datetime.now(UTC)


SYSTEM_CLOCK = SystemClock()

# ADR-0130 section 4: the test override is a ContextVar, so it is task/thread local.
_override: ContextVar[Clock | None] = ContextVar("budget_planner_clock_override", default=None)


def fixed_clock(instant: datetime) -> FixedClock:
    """Build a :class:`FixedClock`; ``instant`` must be timezone-aware."""
    if instant.tzinfo is None:
        msg = "fixed_clock needs a timezone-aware datetime"
        raise ValueError(msg)
    return FixedClock(instant)


def utc_now() -> datetime:
    """Current instant as a timezone-aware UTC datetime."""
    source: Clock = _override.get() or SYSTEM_CLOCK
    return source.now().astimezone(UTC)


def iso_utc(instant: datetime) -> str:
    """Stored timestamp text ``YYYY-MM-DDTHH:MM:SS.mmmZ`` (ms, same as SQLite ``%f``; ADR-0006)."""
    utc = instant.astimezone(UTC)
    return utc.isoformat(timespec="milliseconds").removesuffix("+00:00") + "Z"


def utc_now_iso() -> str:
    """Current instant as stored timestamp text (see :func:`iso_utc`)."""
    return iso_utc(utc_now())


def utc_now_ms() -> datetime:
    """:func:`utc_now` truncated to milliseconds, equal to what the stored text round-trips to."""
    return datetime.fromisoformat(utc_now_iso())


def now_in(tz: str | tzinfo) -> datetime:
    """Current instant converted to ``tz`` (an IANA name or a ``tzinfo``)."""
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    return utc_now().astimezone(zone)


def today(tz: str | tzinfo) -> date:
    """Today's naive calendar date in ``tz`` (ADR-0007)."""
    return now_in(tz).date()


def today_local(settings: HasDisplayTimezone) -> date:
    """Today's date in the configured display timezone."""
    return today(settings.display_timezone)


@contextmanager
def frozen(instant: datetime) -> Iterator[Clock]:
    """Pin the clock to ``instant`` inside the ``with`` block (context-local)."""
    clock = fixed_clock(instant)
    token = _override.set(clock)
    try:
        yield clock
    finally:
        _override.reset(token)
