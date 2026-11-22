"""Daily FX refresh on the FastAPI lifespan (T-Q290, ADR-0145).

Runs once a day after 12:30 Europe/Warsaw and once at startup when no rate is
dated today. Failures are logged and never stop the loop; the cache keeps the
last rates. The blocking fetch runs in a worker thread, like the retention task.
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from budget_planner import clock
from budget_planner.adapters.fx import nbp
from budget_planner.config import Settings
from budget_planner.domain import fx_schedule
from budget_planner.domain.fx import FxFetchError
from budget_planner.domain.ports import RateSource
from budget_planner.logging import get_logger
from budget_planner.services import fx as fx_service
from budget_planner.services.connections import get_connection

MIN_SLEEP_SECONDS: Final = 1.0

SourceOpener = Callable[[Settings], AbstractContextManager[RateSource]]
Sleeper = Callable[[float], Awaitable[None]]


def cache_empty_today(cfg: Settings) -> bool:
    """True when no cached rate is dated today (display timezone)."""
    conn = get_connection(cfg)
    try:
        return not fx_service.has_rate_on(conn, cfg.base_currency, clock.today_local(cfg))
    finally:
        conn.close()


def run_once(cfg: Settings, opener: SourceOpener = nbp.open_source) -> bool:
    """Refresh once; log and return False on failure, never raise for provider/DB errors."""
    log = get_logger("budget_planner.fx_refresh")
    try:
        with opener(cfg) as source:
            conn = get_connection(cfg)
            try:
                result = fx_service.refresh_from_source(
                    conn, source, clock.today_local(cfg), cfg.base_currency
                )
            finally:
                conn.close()
    except (FxFetchError, sqlite3.Error, OSError, ValueError) as exc:
        log.error("fx_refresh_failed", error=str(exc), error_type=type(exc).__name__)
        return False
    if result is None:
        log.info("fx_refresh_no_data")
    else:
        log.info(
            "fx_refresh_done",
            effective_date=result.effective_date.isoformat(),
            inserted=len(result.inserted),
            updated=len(result.updated),
        )
    return True


async def run_forever(
    cfg: Settings,
    *,
    refresh: Callable[[Settings], bool] = run_once,
    missing: Callable[[Settings], bool] = cache_empty_today,
    now: Callable[[], datetime] = clock.utc_now,
    sleep: Sleeper = asyncio.sleep,
) -> None:
    """Refresh at startup if today's rates are missing, then daily after 12:30 local."""
    tz = ZoneInfo(cfg.display_timezone)
    last_ran_on: date | None = None
    run_now = await asyncio.to_thread(missing, cfg)
    while True:
        instant = now()
        due = fx_schedule.is_due(instant, tz, last_ran_on)
        if run_now or due:
            await asyncio.to_thread(refresh, cfg)
            if due:  # a startup run before 12:30 must not consume today's 12:30 run
                last_ran_on = fx_schedule.local_day(instant, tz)
            run_now = False
        wait = (fx_schedule.next_run_at(now(), tz) - now()).total_seconds()
        await sleep(max(wait, MIN_SLEEP_SECONDS))


def start(cfg: Settings) -> asyncio.Task[None] | None:
    """Start the task when enabled (production by default, ``BUDGET_FX_REFRESH_ENABLED``)."""
    if not cfg.daily_refresh_active():
        return None
    return asyncio.create_task(run_forever(cfg), name="fx-refresh")


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
