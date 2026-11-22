"""Upcoming composite service (T-119, ADR-0038).

Union of persisted planned (one-offs, not promoted) + active recurring
rules whose ``next_due`` falls inside the forward window. Overrides on
``next_due`` merge amount / description / date; ``OverrideState.SKIPPED``
excludes the row entirely.

Only planned rows can be ``is_overdue`` (operation_date < today);
recurring rows stay on the promote-and-advance ``next_due`` ladder, so
if their next_due is in the past we still surface them undecorated so
the user can promote them.

Returned items are sorted by effective date; on tie, planned rows come
first so Overview's muted "overdue" chip surfaces before any recurring
row scheduled for the same day.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from typing import Literal

from budget_planner.repositories import recurring as recurring_repo
from budget_planner.services import recurring as recurring_svc
from budget_planner.services.recurring_formula import FormulaFx

UpcomingKind = Literal["planned", "recurring"]


@dataclass(frozen=True, slots=True)
class UpcomingItem:
    """Normalised Upcoming-panel row (ADR-0038 §Overview Upcoming)."""

    kind: UpcomingKind
    effective_date: dt.date
    account_id: int
    dest_account_id: int | None
    category_id: int
    amount_minor: int
    description: str
    is_overdue: bool
    # planned-only fields:
    planned_id: int | None
    # recurring-only fields:
    rule_id: int | None
    override_present: bool
    is_formula: bool


def _item(item: recurring_svc.PendingItem, *, is_formula: bool) -> UpcomingItem:
    """Project one pending item (planned row or ``next_due`` occurrence) for the panel."""
    return UpcomingItem(
        kind=item.kind,
        effective_date=item.due_date,
        account_id=item.account_id,
        dest_account_id=item.dest_account_id,
        category_id=item.category_id,
        amount_minor=item.amount,
        description=item.description,
        # Recurring never surfaces as overdue (module docstring).
        is_overdue=item.is_overdue and item.kind == "planned",
        planned_id=item.planned_id,
        rule_id=item.rule_id,
        override_present=item.is_overridden,
        is_formula=is_formula,
    )


def list_upcoming(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    window_days: int | None,
    fx: FormulaFx,
) -> tuple[UpcomingItem, ...]:
    """Union of persisted planned (not promoted) + each active rule's ``next_due``.

    - ``window_days=None`` -> unbounded forward horizon (used by "All").
    - ``window_days=N`` -> forward horizon of ``today + N`` days (effective date).

    Built on :func:`recurring.pending_occurrences` (overrides, skips, linked-row
    dedup); overdue planned rows stay (``is_overdue``), overdue recurring rows
    surface undecorated so they can be promoted.
    """
    forward_limit = today + dt.timedelta(days=window_days) if window_days is not None else None
    formula_ids = frozenset(
        r.id
        for r in recurring_repo.list_rules(conn, user_id, active_only=True)
        if r.amount_formula is not None
    )
    pending = recurring_svc.pending_occurrences(
        conn,
        user_id,
        fx=fx,
        start=None,
        end=None,
        today=today,
        include_overdue=True,
        next_only=True,
    )
    items = [
        _item(p, is_formula=p.rule_id in formula_ids)
        for p in pending
        if forward_limit is None or p.due_date <= forward_limit
    ]
    items.sort(key=lambda i: (i.effective_date, 0 if i.kind == "planned" else 1))
    return tuple(items)


__all__ = ["UpcomingItem", "UpcomingKind", "list_upcoming"]
