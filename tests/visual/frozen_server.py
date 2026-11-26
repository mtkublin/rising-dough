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

# Handoff fixture (T-UT10, T-UR00b): the designer's sample data (period 7 Oct -> 7 Nov,
# "day 25 of 31", tax refund due 31 Oct, 10 accounts) is shown at this day. The
# handoff-reference comparison serves the base seed of ``tests/visual/handoff_seed.py``
# at this date (ADR-0147 §3); the old-UI route snapshots still use the demo.sqlite copy.
# ``HANDOFF_FIXTURE_DATE`` is the single source for conftest.FROZEN_DATE and
# handoff.HANDOFF_FIXED_TIME.
HANDOFF_FIXTURE_DATE = "2026-10-31"
FROZEN_TIME = dt.time(10, 0)  # 10:00 UTC: same calendar day in Europe/Warsaw


def frozen_instant(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, FROZEN_TIME, tzinfo=dt.UTC)


HANDOFF_ONE_TIME_PASSWORD = "kT4p-9wrx-Lomb"  # noqa: S105 - the board's sample, not a credential  # pragma: allowlist secret


class _HandoffTokens:
    """Token port of the visual server: the generated one-time password is the board's sample.

    Every other token (invites, sessions, CSRF) keeps the CSPRNG. Only the 16-byte request of
    ``services.users.generate_password`` is replaced, so the dialog shows what the handoff shows.
    """

    def new_token(self, nbytes: int) -> str:
        tokens = importlib.import_module("budget_planner.adapters.entropy").SecretsTokenSource()
        return HANDOFF_ONE_TIME_PASSWORD if nbytes == 16 else str(tokens.new_token(nbytes))


def main() -> None:
    raw = os.environ.get("BUDGET_VISUAL_FROZEN_DATE")
    uvicorn = importlib.import_module("uvicorn")  # not in the pre-commit mypy env
    web_app = importlib.import_module("budget_planner.web.app").app
    deps = importlib.import_module("budget_planner.web.deps")
    web_app.dependency_overrides[deps.get_token_source] = _HandoffTokens

    port = int(sys.argv[1])
    with clock.frozen(frozen_instant(dt.date.fromisoformat(raw))) if raw else nullcontext():
        uvicorn.run("budget_planner.web.app:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
