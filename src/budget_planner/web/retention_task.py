"""Daily retention purge on the FastAPI lifespan (T-D60, ADR-0078 §7).

The container entrypoint already purges at start, so the loop sleeps one
interval first and then runs :func:`run_once` in a
worker thread. Failures are logged and never stop the loop; cancellation on
shutdown propagates cleanly (T-D15).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Final

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.logging import RETENTION_LOGGER, get_logger
from budget_planner.services import retention
from budget_planner.services.connections import JOB_ERRORS, get_connection
from budget_planner.web import background_tasks

TASK_NAME: Final = "retention-purge"
PURGE_INTERVAL_SECONDS: Final = 24 * 60 * 60


def run_once(cfg: Settings) -> retention.PurgeResult:
    """Open a connection, purge once at the current instant, close it."""
    conn = get_connection(cfg)
    try:
        return retention.purge(conn, clock.utc_now(), cfg)
    finally:
        conn.close()


async def run_forever(cfg: Settings, interval_seconds: float = PURGE_INTERVAL_SECONDS) -> None:
    log = get_logger(RETENTION_LOGGER)
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(run_once, cfg)
        except JOB_ERRORS as exc:
            log.error("retention_purge_failed", error=str(exc), error_type=type(exc).__name__)


def start(
    cfg: Settings, on_crash: background_tasks.CrashReporter | None = None
) -> asyncio.Task[None]:
    """Start the loop; an unexpected crash is logged and reported, not restarted (T-Q314)."""
    task = asyncio.create_task(run_forever(cfg), name=TASK_NAME)
    return background_tasks.watch(task, on_crash)


async def stop(task: asyncio.Task[None]) -> None:
    if task.done():  # already crashed: logged by the done-callback, don't re-raise at shutdown
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
