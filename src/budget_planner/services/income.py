"""Income-anchor lookup service (T-119, ADR-0038).

Composes planned one-off income + active recurring rules — without
depending on the virtual-recurring union that lived inside
``services.planned.list_planned`` prior to T-119. Overrides on
``rule.next_due`` are honoured via ``recurring_repo.list_overrides``.

Pure w.r.t. DB snapshot; caller injects ``after`` so the budget
service can keep deterministic tests (ADR-0007).
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from budget_planner.services import recurring as recurring_svc
from budget_planner.services.recurring_formula import DATES_ONLY


def next_anchor_date(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    after: dt.date,
    *,
    horizon_days: int = 400,
) -> dt.date | None:
    """Earliest effective date strictly after ``after`` within ``horizon_days``.

    Composes, via :func:`recurring.pending_occurrences`, the unpromoted planned
    rows of ``category_id`` and each active rule's ``next_due`` occurrence
    (overrides applied, skipped dropped, linked-row dedup). Returns ``None``
    when nothing matches inside the horizon.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")

    window_start = after + dt.timedelta(days=1)
    window_end = after + dt.timedelta(days=horizon_days)
    pending = recurring_svc.pending_occurrences(
        conn,
        user_id,
        fx=DATES_ONLY,
        start=None,
        end=None,
        today=after,
        include_overdue=True,
        category_ids=(category_id,),
        next_only=True,
    )
    candidates = [p.due_date for p in pending if window_start <= p.due_date <= window_end]
    return min(candidates) if candidates else None


__all__ = ["next_anchor_date"]
