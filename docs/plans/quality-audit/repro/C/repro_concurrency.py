"""T-Q06 repro: promote is read-then-write outside the transaction (double promote).

Two request threads (each with its own connection, like FastAPI's threadpool) both
read the planned row / recurring rule BEFORE either writes. A threading.Barrier placed
on the validation step (which runs after the read and before the write) forces the
interleaving that a double click or two tabs produce in production.

Scratch DB only. Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-conc.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-conc.sqlite \
      uv run python docs/plans/quality-audit/repro/C/repro_concurrency.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

from budget_planner.config import Settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.services import planned as planned_svc  # noqa: E402
from budget_planner.services import recurring as recurring_svc  # noqa: E402

settings = Settings()
barrier = threading.Barrier(2, timeout=10)
_orig_validate = planned_svc._shared_validate_promotion  # noqa: SLF001
_orig_advance = recurring_svc.advance_next_due


def _validate(*a, **k):  # type: ignore[no-untyped-def]
    barrier.wait()
    return _orig_validate(*a, **k)


def _advance(*a, **k):  # type: ignore[no-untyped-def]
    barrier.wait()
    return _orig_advance(*a, **k)


planned_svc._shared_validate_promotion = _validate  # type: ignore[assignment]  # noqa: SLF001
recurring_svc.advance_next_due = _advance  # type: ignore[assignment]

results: list[str] = []


def run(fn, *args):  # type: ignore[no-untyped-def]
    conn = get_connection(settings)
    try:
        txn = fn(conn, 1, *args)
        results.append(f"ok txn_id={txn.id}")
    except Exception as exc:  # noqa: BLE001
        results.append(f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()


def race(label: str, fn, *args) -> None:  # type: ignore[no-untyped-def]
    results.clear()
    barrier.reset()
    ts = [threading.Thread(target=run, args=(fn, *args)) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    print(f"{label}: {results}")


check = sqlite3.connect(URL.removeprefix("sqlite:///"))
race("planned promote x2 (planned_id=1)", planned_svc.promote_to_actual, 1, planned_svc.PromotionEdits())
n = check.execute("SELECT count(*) FROM transactions WHERE promoted_from_planned_id=1").fetchone()[0]
print("transactions linked to planned #1:", n, "(expected 1)")

# rule 3 is active, next_due 2026-11-15
race("recurring promote x2 (rule_id=3)", recurring_svc.promote_recurring, 3, recurring_svc.PromotionEdits())
n = check.execute(
    "SELECT count(*) FROM transactions WHERE promoted_from_recurring_rule_id=3 "
    "AND promoted_from_recurring_date='2026-11-15'"
).fetchone()[0]
print("transactions for rule #3 occurrence 2026-11-15:", n, "(expected 1)")
