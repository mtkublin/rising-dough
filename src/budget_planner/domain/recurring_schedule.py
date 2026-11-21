"""Pure recurring-cadence scheduling (T-Q243, ADR-0038, ADR-0021).

Owns the canonical occurrence schedule of a recurring rule: ``generate_occurrences``,
``advance_next_due``, ``first_due_on_or_after`` and ``occurrence_in_month``. No I/O, no
clock: callers pass ``today``. Lives in ``domain/`` so repositories (which seed ``next_due``
on insert) and services share it without a repositories -> services import.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

from dateutil.relativedelta import relativedelta

from budget_planner.domain.enums import Cadence, months_per_cadence
from budget_planner.domain.recurring import NewRecurringRule, Occurrence, RecurringRule

_MAX_ITERATIONS = 10_000

# Horizon used by ``first_due_on_or_after`` / ``advance_next_due`` when computing the next
# canonical occurrence. 400 days safely covers monthly, quarterly and yearly cadences.
_LOOKAHEAD_DAYS = 400

# Fixed placeholder timestamp for lookup stubs; the schedule never reads it.
_STUB_TIMESTAMP = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def _step_date(start: dt.date, idx: int, step_months: int, anchor_day: int) -> dt.date:
    """Return ``start + idx * step_months`` anchored on ``anchor_day``.

    ``relativedelta(day=anchor)`` performs the end-of-month clamp automatically.
    For yearly rules with Feb-29 anchor, Feb 28 is produced in non-leap years;
    the cycle recovers to Feb 29 the next time it is possible.
    """
    return start + relativedelta(months=step_months * idx, day=anchor_day)


def _mk_occurrence(rule: RecurringRule, occ_date: dt.date) -> Occurrence:
    return Occurrence(
        rule_id=rule.id,
        occurrence_date=occ_date,
        effective_date=occ_date,
        category_id=rule.category_id,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        amount=rule.default_amount,
        description=rule.default_description,
        is_overridden=False,
        is_skipped=False,
    )


def _base_date(rule: RecurringRule, anchor_day: int) -> dt.date:
    """First schedule anchor: yearly rules honour ``month_of_year`` on-or-after ``start_date``."""
    if rule.cadence is not Cadence.YEARLY or rule.month_of_year is None:
        return rule.start_date
    candidate = rule.start_date + relativedelta(month=rule.month_of_year, day=anchor_day)
    if candidate < rule.start_date:
        candidate = candidate + relativedelta(years=1)
    return candidate


def generate_occurrences(
    rule: RecurringRule,
    range_start: dt.date,
    range_end: dt.date,
) -> tuple[Occurrence, ...]:
    """Return the canonical schedule intersected with ``[range_start, range_end]``.

    Both bounds inclusive. The rule's own ``start_date`` is a candidate
    occurrence. ``active=False`` short-circuits to ``()``. Monthly /
    quarterly / yearly cadences clamp to the end of the month when the
    anchor day exceeds the target month's day count.
    """
    if not rule.active:
        return ()

    hard_end = min(range_end, rule.end_date) if rule.end_date else range_end
    hard_start = max(range_start, rule.start_date)
    if hard_end < hard_start:
        return ()

    step_months = months_per_cadence(rule.cadence)
    # Yearly rules honour an optional month_of_year by anchoring the first
    # occurrence to (month_of_year, day_of_month) on-or-after start_date.
    anchor_day = rule.day_of_month or rule.start_date.day
    base_date = _base_date(rule, anchor_day)

    out: list[Occurrence] = []
    for idx in range(_MAX_ITERATIONS):
        occ_date = _step_date(base_date, idx, step_months, anchor_day)
        if occ_date > hard_end:
            break
        if occ_date >= hard_start:
            out.append(_mk_occurrence(rule, occ_date))
    else:  # pragma: no cover - safety guard
        raise RuntimeError("occurrence generator did not terminate")
    return tuple(out)


def advance_next_due(rule: RecurringRule, from_date: dt.date) -> dt.date | None:
    """Return the next canonical occurrence strictly after ``from_date``.

    Reads the rule's own schedule (anchored on ``rule.start_date`` and
    ``day_of_month``), so the end-of-month clamp never drifts the anchor.
    Returns ``None`` when the next step would exceed ``rule.end_date``.
    """
    end_date = rule.end_date
    hard_end = end_date if end_date is not None else from_date + dt.timedelta(days=_LOOKAHEAD_DAYS)
    if hard_end <= from_date:
        return None
    occs = generate_occurrences(
        dataclasses.replace(rule, active=True),
        from_date + dt.timedelta(days=1),
        hard_end,
    )
    return occs[0].occurrence_date if occs else None


def first_due_on_or_after(rule: RecurringRule, today: dt.date) -> dt.date:
    """Return the earliest canonical occurrence on-or-after ``max(start, today)``.

    Terminal rules (``end_date`` already in the past) return ``rule.start_date`` as a
    sentinel; the repository is responsible for toggling ``active=False`` in that case.
    """
    range_start = max(rule.start_date, today)
    range_end = range_start + dt.timedelta(days=_LOOKAHEAD_DAYS)
    occs = generate_occurrences(rule, range_start, range_end)
    if occs:
        return occs[0].occurrence_date
    return rule.start_date


def _build_lookup_stub(data: NewRecurringRule, user_id: int) -> RecurringRule:
    """Return a throwaway rule carrying only the schedule fields of ``data``."""
    return RecurringRule(
        id=0,
        user_id=user_id,
        cadence=data.cadence,
        start_date=data.start_date,
        end_date=data.end_date,
        category_id=data.category_id,
        account_id=data.account_id,
        dest_account_id=data.dest_account_id,
        default_amount=data.default_amount,
        default_description=data.default_description,
        day_of_month=data.day_of_month,
        month_of_year=data.month_of_year,
        active=True,
        next_due=data.start_date,  # placeholder; the schedule never reads it
        last_promoted_date=None,
        amount_formula=data.amount_formula,
        created_at=_STUB_TIMESTAMP,
        updated_at=_STUB_TIMESTAMP,
        deleted_at=None,
    )


def initial_next_due(data: NewRecurringRule, user_id: int, today: dt.date) -> dt.date:
    """Return the first ``next_due`` for a rule about to be inserted."""
    return first_due_on_or_after(_build_lookup_stub(data, user_id), today)


def occurrence_in_month(rule: RecurringRule, year: int, month: int) -> dt.date | None:
    """Return the canonical occurrence_date that falls in ``(year, month)``.

    Supports the generic override UI (year + month + amount): the user picks
    a target month, the server resolves which canonical occurrence_date to
    key the override on by intersecting the schedule with that calendar
    month. Returns ``None`` if the rule has no occurrence in that month.
    """
    range_start = dt.date(year, month, 1)
    if month == 12:  # noqa: PLR2004 — calendar literal
        range_end = dt.date(year, 12, 31)
    else:
        range_end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    occs = generate_occurrences(rule, range_start, range_end)
    return occs[0].occurrence_date if occs else None
