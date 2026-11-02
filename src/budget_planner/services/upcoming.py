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

from budget_planner.domain.enums import OverrideState
from budget_planner.domain.planned import PlannedFilter, PlannedTransaction
from budget_planner.domain.recurring import RecurringOverride, RecurringRule
from budget_planner.repositories import (
    planned as planned_repo,
    recurring as recurring_repo,
)
from budget_planner.services.recurring_formula import resolve_rule_amount

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


def _planned_item(row: PlannedTransaction, today: dt.date) -> UpcomingItem:
    return UpcomingItem(
        kind="planned",
        effective_date=row.operation_date,
        account_id=row.account_id,
        dest_account_id=row.dest_account_id,
        category_id=row.category_id,
        amount_minor=row.amount,
        description=row.description,
        is_overdue=row.operation_date < today,
        planned_id=row.id,
        rule_id=None,
        override_present=False,
        is_formula=False,
    )


def _recurring_item(
    conn: sqlite3.Connection,
    rule: RecurringRule,
    override: RecurringOverride | None,
) -> UpcomingItem | None:
    """Project an active recurring rule's ``next_due`` into an UpcomingItem.

    Returns ``None`` when the override on ``next_due`` is ``SKIPPED``.
    Formula rules recompute their amount from the current source-rule
    state for the effective date's month (ADR-0047); overrides on the
    amount still win when present.
    """
    if override is not None and override.state is OverrideState.SKIPPED:
        return None
    description = rule.default_description
    effective = rule.next_due
    override_present = False
    amount_override: int | None = None
    if override is not None and override.state is OverrideState.OVERRIDDEN:
        override_present = True
        amount_override = override.amount_override
        if override.description_override is not None:
            description = override.description_override
        if override.date_override is not None:
            effective = override.date_override
    if amount_override is not None:
        amount = amount_override
    else:
        amount = resolve_rule_amount(conn, rule, effective)
    return UpcomingItem(
        kind="recurring",
        effective_date=effective,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        category_id=rule.category_id,
        amount_minor=amount,
        description=description,
        is_overdue=False,  # recurring never surfaces as overdue — see module docstring.
        planned_id=None,
        rule_id=rule.id,
        override_present=override_present,
        is_formula=rule.amount_formula is not None,
    )


def _override_for_next_due(
    conn: sqlite3.Connection,
    rule: RecurringRule,
) -> RecurringOverride | None:
    for override in recurring_repo.list_overrides(conn, rule.id):
        if override.occurrence_date == rule.next_due:
            return override
    return None


def list_upcoming(
    conn: sqlite3.Connection,
    *,
    today: dt.date,
    window_days: int | None,
) -> tuple[UpcomingItem, ...]:
    """Union of persisted planned (not promoted) + active recurring rules.

    - ``window_days=None`` → unbounded forward horizon (used by "All").
    - ``window_days=N`` → forward horizon of ``today + N`` days.

    Soft-deleted + promoted planned rows excluded by the repository
    filter. Recurring rules with ``active=False`` are excluded. Overrides
    on ``rule.next_due`` are applied (merge or skip).
    """
    forward_limit = today + dt.timedelta(days=window_days) if window_days is not None else None

    planned_filter = PlannedFilter(
        date_to=forward_limit,
        promoted=False,
    )
    planned_rows = planned_repo.list_filtered(conn, planned_filter)
    items: list[UpcomingItem] = [_planned_item(row, today) for row in planned_rows]

    for rule in recurring_repo.list_rules(conn, active_only=True):
        # ADR-0063: a rule whose next_due already exceeds its stop date
        # has effectively ended but has not yet been promoted (so advance
        # has not deactivated it). Hide it from Upcoming — the next
        # promotion attempt, or an edit, will clean up the active flag.
        if rule.end_date is not None and rule.next_due > rule.end_date:
            continue
        override = _override_for_next_due(conn, rule)
        projected = _recurring_item(conn, rule, override)
        if projected is None:
            continue
        if forward_limit is not None and projected.effective_date > forward_limit:
            continue
        items.append(projected)

    # Sort by effective_date; break ties by placing planned rows first so
    # the overdue chip ordering stays stable.
    items.sort(key=lambda i: (i.effective_date, 0 if i.kind == "planned" else 1))
    return tuple(items)


__all__ = ["UpcomingItem", "UpcomingKind", "list_upcoming"]
