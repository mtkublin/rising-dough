"""Visual-suite server launcher with a frozen clock (T-VIS5, T-Q229).

``data/demo.sqlite`` is a snapshot whose newest transaction is 2026-10-31.
Pages that key off "today" (fiscal period, days left, overdue tint, relative
dates) therefore drift every day the suite runs. This launcher pins
``budget_planner.clock`` (ADR-0140) for the *test server process only*, then
starts uvicorn.

It lives under ``tests/`` and is started only by ``conftest.live_server``; app
code is untouched and nothing in ``src/`` can reach it, so production
behaviour is unaffected. Opt-in via ``BUDGET_VISUAL_FROZEN_DATE`` (ISO date);
without it the server runs on the real clock.

The override is a ``ContextVar`` set before ``uvicorn.run`` starts the event
loop, so every request task (and its worker threads) inherits it.
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
from contextlib import nullcontext

from budget_planner import clock

FROZEN_TIME = dt.time(10, 0)  # 10:00 UTC: same calendar day in Europe/Warsaw


def frozen_instant(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, FROZEN_TIME, tzinfo=dt.UTC)


def main() -> None:
    raw = os.environ.get("BUDGET_VISUAL_FROZEN_DATE")
    uvicorn = importlib.import_module("uvicorn")  # not in the pre-commit mypy env

    port = int(sys.argv[1])
    with clock.frozen(frozen_instant(dt.date.fromisoformat(raw))) if raw else nullcontext():
        uvicorn.run("budget_planner.web.app:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
