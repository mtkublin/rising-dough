"""The single source of "now" and "today" (ADR-0130 section 4, ADR-0007).

Scaffold only: no caller uses it yet. Migrating call sites is Q-031. Until
then the ruff ``TID251`` ban on ``datetime.date.today``, ``datetime.datetime.now``,
``datetime.datetime.utcnow`` and ``time.time`` is allowlisted per file in
``pyproject.toml``; ``clock.py`` is the one module allowed to read the host
clock.

Rules (ADR-0007):

- Instants are timezone-aware UTC.
- "Today" is a naive ``date`` in the display timezone, never the host's.
- Tests pin time with :func:`frozen`, not by patching ``datetime``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """A zero-argument source of timezone-aware instants."""

    def __call__(self) -> datetime: ...


class HasDisplayTimezone(Protocol):
    """Anything exposing the IANA display timezone (e.g. ``Settings``)."""

    @property
    def display_timezone(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FixedClock:
    """A clock that always returns the same instant (tests, replays)."""

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            msg = "FixedClock needs a timezone-aware datetime"
            raise ValueError(msg)

    def __call__(self) -> datetime:
        return self.instant


_override: ContextVar[Clock | None] = ContextVar("budget_planner_clock_override", default=None)


def _system_now() -> datetime:
    return datetime.now(UTC)


def utc_now() -> datetime:
    """Current instant as a timezone-aware UTC datetime."""
    source: Callable[[], datetime] = _override.get() or _system_now
    return source().astimezone(UTC)


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
    clock = FixedClock(instant)
    token = _override.set(clock)
    try:
        yield clock
    finally:
        _override.reset(token)
