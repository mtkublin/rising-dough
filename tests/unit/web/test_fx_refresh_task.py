"""In-app daily FX refresh task (T-Q290, ADR-0145): injected clock, sleep and refresh."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.domain.fx import FxFetchError, RateTable
from budget_planner.domain.ports import RateSource
from budget_planner.web import fx_refresh_task
from tests.db_template import sqlite_url

SETTINGS = Settings(_env_file=None, env="test")


def _drive(
    start: datetime, *, missing: bool, sleeps_before_stop: int
) -> tuple[list[datetime], list[float]]:
    """Run the loop on a fake clock; returns (refresh instants, sleep seconds)."""
    current = [start]
    ran: list[datetime] = []
    slept: list[float] = []

    def refresh(_cfg: Settings) -> bool:
        ran.append(current[0])
        return True

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) >= sleeps_before_stop:
            raise asyncio.CancelledError
        current[0] += timedelta(seconds=seconds)

    async def scenario() -> None:
        await fx_refresh_task.run_forever(
            SETTINGS,
            refresh=refresh,
            missing=lambda _c: missing,
            now=lambda: current[0],
            sleep=sleep,
        )

    errors: list[BaseException] = []

    def target() -> None:
        try:
            asyncio.run(scenario())
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    worker = threading.Thread(target=target)
    worker.start()
    worker.join(timeout=30)
    assert len(errors) == 1
    assert isinstance(errors[0], asyncio.CancelledError)
    return ran, slept


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_does_nothing_before_1230_then_runs_once_after_and_not_again_same_day() -> None:
    start = _utc(2026, 1, 15, 8, 0)  # 09:00 Warsaw; first pass is not due
    ran, slept = _drive(start, missing=False, sleeps_before_stop=3)
    assert ran == [_utc(2026, 1, 15, 11, 30), _utc(2026, 1, 16, 11, 30)]
    assert slept == [3.5 * 3600, 24 * 3600, 24 * 3600]


def test_startup_run_when_rates_missing_even_before_1230() -> None:
    start = _utc(2026, 1, 15, 8, 0)
    ran, _ = _drive(start, missing=True, sleeps_before_stop=2)
    assert ran == [start, _utc(2026, 1, 15, 11, 30)]


def test_started_after_1230_runs_once_then_waits_for_next_day() -> None:
    start = _utc(2026, 1, 15, 14, 0)
    ran, slept = _drive(start, missing=False, sleeps_before_stop=2)
    assert ran == [start, _utc(2026, 1, 16, 11, 30)]
    assert slept[0] == 21.5 * 3600


def test_schedule_shifts_with_dst() -> None:
    start = _utc(2026, 3, 28, 12, 0)  # 13:00 CET
    ran, _ = _drive(start, missing=True, sleeps_before_stop=2)
    assert ran == [start, _utc(2026, 3, 29, 10, 30)]  # CEST: 12:30 local is 10:30Z


class _Source:
    def __init__(self, table: RateTable | None, error: str | None = None) -> None:
        self.table = table
        self.error = error

    def latest_table(self) -> RateTable | None:
        if self.error:
            raise FxFetchError(self.error)
        return self.table


def _opener(source: _Source) -> fx_refresh_task.SourceOpener:
    @contextmanager
    def opener(_cfg: Settings) -> Iterator[RateSource]:
        yield source

    return opener


@pytest.fixture
def db_settings(migrated_db: Path) -> Settings:
    return Settings(_env_file=None, env="test", database_url=sqlite_url(migrated_db))


def test_run_once_failure_returns_false_and_cache_unchanged(db_settings: Settings) -> None:
    assert fx_refresh_task.run_once(db_settings, _opener(_Source(None, "down"))) is False
    assert fx_refresh_task.cache_empty_today(db_settings)


def test_run_once_no_data_is_ok(db_settings: Settings) -> None:
    assert fx_refresh_task.run_once(db_settings, _opener(_Source(None))) is True


@pytest.mark.parametrize(("flag", "expected"), [(None, False), (True, True), (False, False)])
def test_enabled_toggle_non_production(flag: bool | None, expected: bool) -> None:
    cfg = Settings(_env_file=None, env="test", fx_refresh_enabled=flag)
    assert cfg.daily_refresh_active() is expected


def test_disabled_task_is_not_started() -> None:
    assert fx_refresh_task.start(SETTINGS) is None
