"""Recurring occurrence generator + promotion orchestrator (T-022 / T-118).

The pure-function surface (``generate_occurrences`` / ``apply_overrides`` /
``expand``) is unchanged from T-022 — it still touches no DB; callers resolve
the rule and its overrides and pass them in. Downstream consumers (planned
log, forecast, recurring router) call :func:`expand` as a one-liner.

T-118 adds the promotion lifecycle (ADR-0038): ``advance_next_due`` +
``first_due_on_or_after`` are pure cadence helpers; ``promote_recurring`` +
``skip_and_advance`` orchestrate single-DB-transaction mutations against the
recurring repository, the transactions repository, and the audit log.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta

from budget_planner.domain.enums import Cadence, OverrideState
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    Occurrence,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.transactions import NewTransaction, Transaction

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 10_000

_STEP_MONTHS: dict[Cadence, int] = {
    Cadence.MONTHLY: 1,
    Cadence.QUARTERLY: 3,
    Cadence.YEARLY: 12,
}

# Horizon used by ``first_due_on_or_after`` / ``advance_next_due`` when
# computing the next canonical occurrence. 400 days safely covers monthly,
# quarterly, and yearly cadences in a single generator pass.
_LOOKAHEAD_DAYS = 400


# ---------------------------------------------------------------------------
# Promotion edit DTO + error classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PromotionEdits:
    """Explicit per-call overrides merged on top of override + default values."""

    operation_date: dt.date | None = None
    amount_minor: int | None = None
    description: str | None = None


class RecurringNotFoundError(LookupError):
    """Raised when the rule_id does not exist (or is soft-deleted)."""


class InactiveRecurringError(RuntimeError):
    """Raised when attempting to promote an inactive (deactivated) rule."""


class CannotPromoteSkippedError(RuntimeError):
    """Raised when the next-due occurrence has a ``state=skipped`` override.

    The user must first delete the override (or wait for next_due to
    advance via ``skip_and_advance``) before promoting the rule.
    """


# ---------------------------------------------------------------------------
# Pure cadence helpers
# ---------------------------------------------------------------------------
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

    step_months = _STEP_MONTHS[rule.cadence]
    # Yearly rules honour an optional month_of_year by anchoring the first
    # occurrence to (month_of_year, day_of_month) on-or-after start_date.
    anchor_day = rule.day_of_month or rule.start_date.day
    base_date = rule.start_date
    if rule.cadence is Cadence.YEARLY and rule.month_of_year is not None:
        candidate = base_date + relativedelta(month=rule.month_of_year, day=anchor_day)
        if candidate < rule.start_date:
            candidate = candidate + relativedelta(years=1)
        base_date = candidate

    out: list[Occurrence] = []
    for idx in range(_MAX_ITERATIONS):
        occ_date = _step_date(base_date, idx, step_months, anchor_day)
        if occ_date > hard_end:
            break
        if occ_date >= range_start:
            out.append(_mk_occurrence(rule, occ_date))
    else:  # pragma: no cover - safety guard
        raise RuntimeError("occurrence generator did not terminate")
    return tuple(out)


def _apply_single_override(occ: Occurrence, override: RecurringOverride) -> Occurrence | None:
    """Return the overridden occurrence, or ``None`` if ``state=skipped``."""
    if override.state is OverrideState.SKIPPED:
        return None
    new_amount = override.amount_override if override.amount_override is not None else occ.amount
    new_description = (
        override.description_override
        if override.description_override is not None
        else occ.description
    )
    new_effective = (
        override.date_override if override.date_override is not None else occ.occurrence_date
    )
    return Occurrence(
        rule_id=occ.rule_id,
        occurrence_date=occ.occurrence_date,  # canonical key preserved
        effective_date=new_effective,
        category_id=occ.category_id,
        account_id=occ.account_id,
        dest_account_id=occ.dest_account_id,
        amount=new_amount,
        description=new_description,
        is_overridden=True,
        is_skipped=False,
    )


def apply_overrides(
    occurrences: Sequence[Occurrence],
    overrides: Iterable[RecurringOverride],
) -> tuple[Occurrence, ...]:
    """Apply the ``(skipped | overridden)`` state machine.

    Keyed by the ORIGINAL ``occurrence_date``, not the overridden one. Orphan
    overrides (no matching canonical occurrence) are dropped with a DEBUG log.
    Duplicates on the same key log a WARNING; last-wins by sort order on ``id``.
    """
    # Group overrides by occurrence_date, warn on duplicates.
    by_date: dict[dt.date, RecurringOverride] = {}
    seen: set[dt.date] = set()
    canonical_dates = {o.occurrence_date for o in occurrences}
    for override in sorted(overrides, key=lambda o: o.id):
        if override.occurrence_date in seen:
            logger.warning(
                "overrides collide on (rule_id=%s, occurrence_date=%s); last-wins",
                override.rule_id,
                override.occurrence_date,
            )
        seen.add(override.occurrence_date)
        if override.occurrence_date not in canonical_dates:
            logger.debug(
                "orphan override dropped: rule_id=%s date=%s",
                override.rule_id,
                override.occurrence_date,
            )
            continue
        by_date[override.occurrence_date] = override

    out: list[Occurrence] = []
    for occ in occurrences:
        match = by_date.get(occ.occurrence_date)
        if match is None:
            out.append(occ)
            continue
        updated = _apply_single_override(occ, match)
        if updated is not None:
            out.append(updated)
    # Sort by effective_date (overrides may shift dates), stable on occurrence_date.
    out.sort(key=lambda o: (o.effective_date, o.occurrence_date))
    return tuple(out)


def expand(
    rule: RecurringRule,
    overrides: Iterable[RecurringOverride],
    range_start: dt.date,
    range_end: dt.date,
) -> tuple[Occurrence, ...]:
    """``generate_occurrences(...)`` then ``apply_overrides(...)``."""
    return apply_overrides(generate_occurrences(rule, range_start, range_end), overrides)


# ---------------------------------------------------------------------------
# T-118: pure next-due helpers
# ---------------------------------------------------------------------------
def _build_lookup_stub(
    *,
    cadence: Cadence,
    start_date: dt.date,
    end_date: dt.date | None,
    day_of_month: int | None,
    month_of_year: int | None,
) -> RecurringRule:
    """Build a synthetic ``RecurringRule`` for pure cadence calculations.

    The stub carries only the fields the generator reads; the DB-tied
    columns (``user_id``, timestamps, ``id``) take placeholder values that
    never surface because the stub is thrown away after one pass.
    """
    now = dt.datetime.now(dt.UTC)
    return RecurringRule(
        id=0,
        user_id=0,
        cadence=cadence,
        start_date=start_date,
        end_date=end_date,
        category_id=0,
        account_id=0,
        dest_account_id=None,
        default_amount=0,
        default_description="",
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        active=True,
        next_due=start_date,
        last_promoted_date=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def advance_next_due(
    cadence: Cadence,
    from_date: dt.date,
    end_date: dt.date | None,
    day_of_month: int | None,
    month_of_year: int | None,
) -> dt.date | None:
    """Return the next canonical occurrence strictly after ``from_date``.

    End-of-month clamp (31 → 28/29/30) and the Feb-29 leap-year anchor are
    delegated to ``generate_occurrences`` so the cadence maths lives in one
    place. Returns ``None`` when the next step would exceed ``end_date``.
    """
    # The generator's canonical schedule anchors on the rule's ``start_date``.
    # To return "strictly after from_date", shift the stub's start_date to
    # from_date so the generator produces the right cadence; then look for
    # the first candidate strictly > from_date.
    stub = _build_lookup_stub(
        cadence=cadence,
        start_date=from_date,
        end_date=end_date,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
    )
    hard_end = end_date if end_date is not None else from_date + dt.timedelta(days=_LOOKAHEAD_DAYS)
    if hard_end <= from_date:
        return None
    occs = generate_occurrences(
        stub,
        from_date + dt.timedelta(days=1),
        hard_end,
    )
    if not occs:
        return None
    return occs[0].occurrence_date


def first_due_on_or_after(rule: RecurringRule, today: dt.date) -> dt.date:
    """Return the earliest canonical occurrence on-or-after ``max(start, today)``.

    Used by ``repositories.recurring.create_rule`` to seed ``next_due`` on
    insert and by the T-117 migration backfill. Terminal rules (``end_date``
    already in the past) return ``rule.start_date`` as a sentinel — the
    repository is responsible for toggling ``active=False`` in that case.
    """
    range_start = max(rule.start_date, today)
    range_end = range_start + dt.timedelta(days=_LOOKAHEAD_DAYS)
    occs = generate_occurrences(rule, range_start, range_end)
    if occs:
        return occs[0].occurrence_date
    return rule.start_date


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


# ---------------------------------------------------------------------------
# T-118: promotion orchestrator
# ---------------------------------------------------------------------------
def _resolve_override_for_next_due(
    overrides: Iterable[RecurringOverride],
    due_date: dt.date,
) -> RecurringOverride | None:
    """Return the override whose canonical ``occurrence_date == due_date``."""
    for override in overrides:
        if override.occurrence_date == due_date:
            return override
    return None


def promote_recurring(
    conn: sqlite3.Connection,
    rule_id: int,
    edits: PromotionEdits,
) -> Transaction:
    """Promote the next-due occurrence of a recurring rule to an actual txn.

    Behaviour per ADR-0038 §Promotion flow:

    1. Load rule (active + non-deleted guards).
    2. ``due_date = rule.next_due``.
    3. Lookup override for ``(rule_id, due_date)``:
       - ``skipped`` → raise ``CannotPromoteSkippedError``.
       - ``overridden`` → merge amount / description / date defaults.
    4. Overlay explicit ``edits``.
    5. Validate direction via shared validator (currency match for transit,
       zero-amount guard, adjustment-direction rejection).
    6. Single DB transaction:
       - Insert ``transactions`` row with recurring provenance stamped.
       - Advance ``next_due`` (or deactivate rule when ``end_date`` passed).
       - Delete the matching override row (its purpose is served).
       - Audit entry on the rule mutation.
    7. Return the new ``Transaction``.
    """
    # Lazy imports — ``repositories.recurring`` imports ``services.recurring``
    # for ``generate_occurrences`` at module load, so top-level imports here
    # would introduce a circular dependency.
    from budget_planner.repositories import (  # noqa: PLC0415
        categories as categories_repo,
        recurring as recurring_repo,
        transactions as transactions_repo,
    )
    from budget_planner.repositories._shared import transaction as db_transaction  # noqa: PLC0415
    from budget_planner.services import audit as audit_svc  # noqa: PLC0415
    from budget_planner.services._promotion import (  # noqa: PLC0415
        ValidationError,
        validate_promotion,
    )

    rule = recurring_repo.find_rule(conn, rule_id)
    if rule is None:
        raise RecurringNotFoundError(rule_id)
    if not rule.active:
        raise InactiveRecurringError(rule_id)

    due_date = rule.next_due
    overrides = recurring_repo.list_overrides(conn, rule_id)
    match = _resolve_override_for_next_due(overrides, due_date)

    # Defaults start from the rule. Formula rules recompute from the
    # live source-rule state for the next_due month (ADR-0045).
    from budget_planner.services.recurring_formula import (  # noqa: PLC0415
        resolve_rule_amount,
    )

    default_amount = resolve_rule_amount(conn, rule, due_date)
    default_description = rule.default_description
    effective_date = due_date
    if match is not None:
        if match.state is OverrideState.SKIPPED:
            raise CannotPromoteSkippedError(rule_id)
        if match.amount_override is not None:
            default_amount = match.amount_override
        if match.description_override is not None:
            default_description = match.description_override
        if match.date_override is not None:
            effective_date = match.date_override

    # Explicit edits overlay the override-derived defaults.
    operation_date = edits.operation_date or effective_date
    amount = edits.amount_minor if edits.amount_minor is not None else default_amount
    description = edits.description if edits.description is not None else default_description

    # ADR-0047: formulas may resolve to zero or negative when term sums
    # cancel. User-explicit edits (``edits.amount_minor``) take precedence,
    # so the guard only trips on live-formula resolution.
    if rule.amount_formula is not None and edits.amount_minor is None and amount <= 0:
        raise ValidationError(
            "formula resolved to a non-positive amount — "
            "edit the formula or override this occurrence"
        )

    category = categories_repo.find_by_id(conn, rule.category_id, include_deleted=True)
    if category is None:  # pragma: no cover - FK guarantees existence
        raise ValidationError(f"category {rule.category_id} not found")

    validate_promotion(
        conn,
        direction=category.direction,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        amount=amount,
    )

    new_txn = NewTransaction(
        operation_date=operation_date,
        category_id=rule.category_id,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        amount=amount,
        description=description,
        promoted_from_recurring_rule_id=rule_id,
        promoted_from_recurring_date=due_date,
    )

    new_next_due = advance_next_due(
        rule.cadence,
        due_date,
        rule.end_date,
        rule.day_of_month,
        rule.month_of_year,
    )

    with db_transaction(conn):
        txn = transactions_repo.create(conn, new_txn)
        if new_next_due is None:
            recurring_repo.set_inactive(conn, rule_id)
        else:
            recurring_repo.set_next_due(
                conn,
                rule_id,
                next_due=new_next_due,
                last_promoted_date=due_date,
            )
        if match is not None:
            # ADR-0046: soft-consume the override by stamping the new txn id
            # instead of deleting the row. Keeps the override visible to
            # historical reads (formula compute per ADR-0045).
            recurring_repo.mark_override_promoted(conn, match.id, txn_id=txn.id)
        updated_rule = recurring_repo.find_rule(conn, rule_id, include_deleted=True)
        audit_svc.write_audit(
            conn,
            entity_type="recurring_rule",
            entity_id=rule_id,
            operation="update",
            prev=rule,
            new=updated_rule,
        )
    return txn


def skip_and_advance(
    conn: sqlite3.Connection,
    rule_id: int,
) -> dt.date | None:
    """Skip the next-due occurrence and advance ``next_due`` without promoting.

    Writes a ``state=skipped`` override, advances ``next_due`` to the
    following canonical occurrence (or deactivates the rule when the
    advancement would exceed ``end_date``), and then deletes the just-
    written skip override — its purpose is served by the advancement.
    ``last_promoted_date`` is unchanged (a skip is not a promotion).
    Returns the new ``next_due`` or ``None`` when the rule was deactivated.
    """
    from budget_planner.repositories import recurring as recurring_repo  # noqa: PLC0415
    from budget_planner.repositories._shared import transaction as db_transaction  # noqa: PLC0415
    from budget_planner.services import audit as audit_svc  # noqa: PLC0415

    rule = recurring_repo.find_rule(conn, rule_id)
    if rule is None:
        raise RecurringNotFoundError(rule_id)
    if not rule.active:
        raise InactiveRecurringError(rule_id)

    due_date = rule.next_due
    new_next_due = advance_next_due(
        rule.cadence,
        due_date,
        rule.end_date,
        rule.day_of_month,
        rule.month_of_year,
    )

    with db_transaction(conn):
        # Record the skip (audit emitted by the override upsert path).
        recurring_repo.upsert_override(
            conn,
            NewRecurringOverride(
                rule_id=rule_id,
                occurrence_date=due_date,
                state=OverrideState.SKIPPED,
            ),
        )
        if new_next_due is None:
            recurring_repo.set_inactive(conn, rule_id)
        else:
            recurring_repo.set_next_due(
                conn,
                rule_id,
                next_due=new_next_due,
                last_promoted_date=rule.last_promoted_date,
            )
        # The skip override has served its purpose — remove it so the next
        # occurrence isn't re-skipped if ``next_due`` ever cycles back.
        recurring_repo.delete_override(conn, rule_id, due_date)
        updated_rule = recurring_repo.find_rule(conn, rule_id, include_deleted=True)
        audit_svc.write_audit(
            conn,
            entity_type="recurring_rule",
            entity_id=rule_id,
            operation="update",
            prev=rule,
            new=updated_rule,
        )
    return new_next_due


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0038)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BatchPromoteResult:
    """Summary of a batch recurring promote-due pass.

    ``promoted_txn_ids`` carries the id of every transaction created.
    ``advanced_rule_ids`` carries the id of every rule whose ``next_due``
    was advanced (one per promotion). ``skipped_rule_ids`` carries the id
    of every active due rule that was intentionally not promoted (e.g. a
    skipped override on next_due).
    """

    promoted_txn_ids: tuple[int, ...]
    advanced_rule_ids: tuple[int, ...]
    skipped_rule_ids: tuple[int, ...]


def batch_promote_due(
    conn: sqlite3.Connection,
    today: dt.date,
) -> BatchPromoteResult:
    """Promote every active rule whose ``next_due`` is on-or-before ``today``.

    Runs inside a single DB transaction. If any inner promote raises
    (``ValidationError`` from a formula resolving to a non-positive amount,
    etc.), the whole batch rolls back. Skipped-override rows advance via
    :func:`skip_and_advance` so the caller does not have to re-run the
    batch after a skip.
    """
    from budget_planner.repositories import recurring as recurring_repo  # noqa: PLC0415
    from budget_planner.repositories._shared import transaction as db_transaction  # noqa: PLC0415

    promoted: list[int] = []
    advanced: list[int] = []
    skipped: list[int] = []
    with db_transaction(conn):
        for rule in recurring_repo.list_rules(conn, active_only=True):
            if rule.next_due > today:
                continue
            override = _resolve_override_for_next_due(
                recurring_repo.list_overrides(conn, rule.id), rule.next_due
            )
            from budget_planner.domain.enums import OverrideState  # noqa: PLC0415

            if override is not None and override.state is OverrideState.SKIPPED:
                # Advance past the skip without creating a transaction.
                skip_and_advance(conn, rule.id)
                skipped.append(rule.id)
                continue
            txn = promote_recurring(conn, rule.id, PromotionEdits())
            promoted.append(txn.id)
            advanced.append(rule.id)
    return BatchPromoteResult(
        promoted_txn_ids=tuple(promoted),
        advanced_rule_ids=tuple(advanced),
        skipped_rule_ids=tuple(skipped),
    )


# Re-export the runtime-aware expand so callers that need formula substitution
# can grab it from the main service module alongside the pure helpers.
from budget_planner.services.recurring_formula import (  # noqa: E402
    resolve_rule_amount,
    rt_expand,
)

__all__ = [
    "BatchPromoteResult",
    "CannotPromoteSkippedError",
    "InactiveRecurringError",
    "PromotionEdits",
    "RecurringNotFoundError",
    "advance_next_due",
    "apply_overrides",
    "batch_promote_due",
    "expand",
    "first_due_on_or_after",
    "generate_occurrences",
    "occurrence_in_month",
    "promote_recurring",
    "resolve_rule_amount",
    "rt_expand",
    "skip_and_advance",
]
