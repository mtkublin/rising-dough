"""Crash visibility for lifespan background tasks (T-Q314, ADR-0130 amendment 2026-11-23).

The retention and FX loops catch only their expected job errors (T-Q271); anything
else ends the task. Nothing awaits it before shutdown, so a done-callback logs the
crash and reports the task name to the app, which keeps serving and does not restart
the job (fail loudly; the operator restarts or deploys).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial

from budget_planner.logging import get_logger

CrashReporter = Callable[[str], None]


def _on_done(on_crash: CrashReporter | None, task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    name = task.get_name()
    get_logger("budget_planner.background").error(
        "background_task_crashed", task=name, error_type=type(exc).__name__, exc_info=exc
    )
    if on_crash is not None:
        on_crash(name)


def watch(task: asyncio.Task[None], on_crash: CrashReporter | None = None) -> asyncio.Task[None]:
    """Attach the crash callback (cancellation is silent) and return the task."""
    task.add_done_callback(partial(_on_done, on_crash))
    return task
