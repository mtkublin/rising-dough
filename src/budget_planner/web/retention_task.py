"""Daily retention purge on the FastAPI lifespan (T-D60, ADR-0078 §7).

The container entrypoint already purges at start, so the loop sleeps one
interval first and then runs :func:`budget_planner.db.retention.run` in a
worker thread. Failures are logged and never stop the loop; cancellation on
shutdown propagates cleanly (T-D15).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Final

from budget_planner.config import Settings
from budget_planner.db import retention
from budget_planner.logging import get_logger

PURGE_INTERVAL_SECONDS: Final = 24 * 60 * 60


async def run_forever(cfg: Settings, interval_seconds: float = PURGE_INTERVAL_SECONDS) -> None:
    log = get_logger("budget_planner.retention")
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(retention.run, cfg)
        except Exception as exc:
            log.error("retention_purge_failed", error=str(exc), error_type=type(exc).__name__)


def start(cfg: Settings) -> asyncio.Task[None]:
    return asyncio.create_task(run_forever(cfg), name="retention-purge")


async def stop(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
