"""Visual-suite server launcher with a frozen wall clock (T-VIS5).

``data/demo.sqlite`` is a snapshot whose newest transaction is 2026-10-31.
Pages that key off "today" (fiscal period, days left, overdue tint, relative
dates) therefore drift every day the suite runs. This launcher pins
``datetime.date.today()`` / ``datetime.datetime.now()`` for the *test server
process only*, then starts uvicorn.

It lives under ``tests/`` and is started only by ``conftest.live_server``; app
code is untouched and nothing in ``src/`` can reach it, so production
behaviour is unaffected. Opt-in via ``BUDGET_VISUAL_FROZEN_DATE`` (ISO date);
without it the server runs on the real clock.

The patch must run before ``budget_planner`` is imported, because modules do
``from datetime import date`` and would otherwise keep the real classes.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import os
import sys

FROZEN_TIME = _dt.time(10, 0)  # 10:00 UTC: same calendar day in Europe/Warsaw
_REAL_DATE = _dt.date
_REAL_DATETIME = _dt.datetime


def _frozen_utc(day: _dt.date) -> _dt.datetime:
    return _REAL_DATETIME.combine(day, FROZEN_TIME, tzinfo=_dt.UTC)


def install(day: _dt.date) -> None:
    """Replace ``datetime.date`` / ``datetime.datetime`` with frozen look-alikes."""
    frozen = _frozen_utc(day)

    class _DateMeta(type):
        def __instancecheck__(cls, obj: object) -> bool:
            return isinstance(obj, _REAL_DATE)

    class FrozenDate(_REAL_DATE, metaclass=_DateMeta):
        @classmethod
        def today(cls) -> _dt.date:  # type: ignore[override]
            return _REAL_DATE(day.year, day.month, day.day)

    class _DateTimeMeta(type):
        def __instancecheck__(cls, obj: object) -> bool:
            return isinstance(obj, _REAL_DATETIME)

    class FrozenDateTime(_REAL_DATETIME, metaclass=_DateTimeMeta):
        @classmethod
        def now(cls, tz: _dt.tzinfo | None = None) -> _dt.datetime:  # type: ignore[override]
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

        @classmethod
        def today(cls) -> _dt.datetime:  # type: ignore[override]
            return frozen.replace(tzinfo=None)

    _dt.date = FrozenDate  # type: ignore[misc]
    _dt.datetime = FrozenDateTime  # type: ignore[misc]


def main() -> None:
    raw = os.environ.get("BUDGET_VISUAL_FROZEN_DATE")
    if raw:
        # These bind/subclass the real datetime types at import time (C-API
        # caches in pandas, `class X(date)` in pydantic.v1); load them first.
        import pandas  # noqa: F401, PLC0415
        import pydantic.v1  # noqa: F401, PLC0415

        install(_REAL_DATE.fromisoformat(raw))
    uvicorn = importlib.import_module("uvicorn")  # not in the pre-commit mypy env

    port = int(sys.argv[1])
    uvicorn.run("budget_planner.web.app:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
