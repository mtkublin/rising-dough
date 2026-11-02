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

from budget_planner.domain.enums import OverrideState
from budget_planner.domain.planned import PlannedFilter
from budget_planner.repositories import (
    planned as planned_repo,
    recurring as recurring_repo,
)


def _recurring_candidate_date(
    conn: sqlite3.Connection,
    rule_id: int,
    next_due: dt.date,
) -> dt.date | None:
    """Return the effective date for ``rule.next_due`` after override lookup.

    ``OverrideState.SKIPPED`` on ``next_due`` → ``None`` (row excluded).
    ``OverrideState.OVERRIDDEN`` with a non-null ``date_override`` → the
    override's shifted date. Otherwise the canonical ``next_due`` stands.
    """
    for override in recurring_repo.list_overrides(conn, rule_id):
        if override.occurrence_date != next_due:
            continue
        if override.state is OverrideState.SKIPPED:
            return None
        if override.state is OverrideState.OVERRIDDEN and override.date_override is not None:
            return override.date_override
        return next_due
    return next_due


def next_anchor_date(
    conn: sqlite3.Connection,
    category_id: int,
    after: dt.date,
    *,
    horizon_days: int = 400,
) -> dt.date | None:
    """Earliest effective date strictly after ``after`` within ``horizon_days``.

    Composes:
      - persisted one-off planned rows (``promoted=False``,
        ``category_ids=(category_id,)``) via ``planned_repo.list_filtered``.
      - active recurring rules filtered client-side on ``category_id``,
        reading ``rule.next_due`` directly (ADR-0038). Override on
        ``next_due`` is applied via ``_recurring_candidate_date``.

    Returns ``None`` when nothing matches inside the horizon.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be >= 1")

    window_start = after + dt.timedelta(days=1)
    window_end = after + dt.timedelta(days=horizon_days)

    # Persisted one-offs.
    planned_rows = planned_repo.list_filtered(
        conn,
        PlannedFilter(
            date_from=window_start,
            date_to=window_end,
            category_ids=(category_id,),
            promoted=False,
        ),
    )
    candidates: list[dt.date] = [row.operation_date for row in planned_rows]

    # Active recurring rules — honour overrides on ``next_due``.
    for rule in recurring_repo.list_rules(conn, active_only=True):
        if rule.category_id != category_id:
            continue
        effective = _recurring_candidate_date(conn, rule.id, rule.next_due)
        if effective is None:
            continue
        if window_start <= effective <= window_end:
            candidates.append(effective)

    if not candidates:
        return None
    return min(candidates)


__all__ = ["next_anchor_date"]
