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

import dataclasses
import datetime as dt
import sqlite3
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from budget_planner.domain.enums import Direction, OverrideState
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    Occurrence,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.recurring_schedule import (
    advance_next_due,
    first_due_on_or_after,
    generate_occurrences,
    occurrence_in_month,
)
from budget_planner.domain.transactions import NewTransaction, Transaction
from budget_planner.repositories import (
    audit as audit_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
)
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.repositories._unaudited import (
    clear_override_promoted,
    mark_override_promoted,
    restore_rule_progress,
    set_inactive,
    set_next_due,
)
from budget_planner.services import audit as audit_svc
from budget_planner.services._promotion import (
    ValidationError,
    create_promoted_transaction,
    validate_promotion,
)
from budget_planner.services.recurring_formula import (
    DatesOnly,
    FormulaFx,
    resolve_rule_amount,
    rt_expand,
)
from budget_planner.services.recurring_overrides import apply_overrides
from budget_planner.services.recurring_rules import (
    create_rule,
    deactivate_rule,
    delete_override,
    find_rule,
    list_overrides,
    list_rules,
    update_rule,
    upsert_override,
)


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
# T-118 / T-Q211: pure next-due helpers (ADR-0038 amendment 2026-11-21)
# ---------------------------------------------------------------------------
def default_day_of_month(start_date: dt.date, day_of_month: int | None) -> int:
    """Return the persisted schedule anchor: explicit day, else the start day."""
    return day_of_month if day_of_month is not None else start_date.day


def with_anchor_day(data: NewRecurringRule) -> NewRecurringRule:
    """Return ``data`` with ``day_of_month`` defaulted to ``start_date.day`` (Q-006)."""
    return dataclasses.replace(
        data, day_of_month=default_day_of_month(data.start_date, data.day_of_month)
    )


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
    user_id: int,
    rule_id: int,
    edits: PromotionEdits,
    *,
    fx: FormulaFx,
) -> Transaction:
    """Promote the next-due occurrence of a recurring rule to an actual txn.

    Behaviour per ADR-0038 §Promotion flow:

    1. Load rule (active + non-deleted guards).
    2. ``due_date = rule.next_due``.
    3. Lookup override for ``(rule_id, due_date)``:
       - ``skipped`` → raise ``CannotPromoteSkippedError``.
       - ``overridden`` → merge amount / description / date defaults.
    4. Overlay explicit ``edits`` (a formula converts through ``fx``, T-Q286).
    5. Validate direction via shared validator (currency match for transit,
       zero-amount guard, adjustment-direction rejection).
    6. Single DB transaction: insert the txn (recurring provenance stamped), advance
       ``next_due`` (or deactivate past ``end_date``), consume the override, audit the rule.
    7. Return the new ``Transaction``.
    """
    # ADR-0137: guard reads and writes share one write-locked transaction.
    with db_transaction(conn):
        rule = _load_active_rule(conn, user_id, rule_id)
        due_date = rule.next_due
        overrides = recurring_repo.list_overrides(conn, user_id, rule_id)
        match = _resolve_override_for_next_due(overrides, due_date)
        amount, description, operation_date = _promotion_values(
            conn, user_id, rule, due_date, match=match, edits=edits, fx=fx
        )

        new_txn = _validated_promotion_txn(
            conn,
            user_id,
            rule,
            due_date,
            amount=amount,
            description=description,
            operation_date=operation_date,
        )
        txn = create_promoted_transaction(conn, user_id, new_txn)
        _advance_rule(conn, user_id, rule, due_date, last_promoted_date=due_date)
        if match is not None:
            # ADR-0046: soft-consume (stamp the txn id) so formula history keeps seeing it.
            mark_override_promoted(conn, user_id, match.id, txn_id=txn.id)
        _audit_rule_update(conn, user_id, rule)
    return txn


def _validated_promotion_txn(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    due_date: dt.date,
    *,
    amount: int,
    description: str,
    operation_date: dt.date,
) -> NewTransaction:
    """Validate the promotion (direction, currency, amount) and build the new transaction."""
    category = categories_repo.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    if category is None:  # pragma: no cover - FK guarantees existence
        raise ValidationError(f"category {rule.category_id} not found")
    validate_promotion(
        conn,
        user_id,
        direction=category.direction,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        amount=amount,
    )
    return NewTransaction(
        operation_date=operation_date,
        category_id=rule.category_id,
        account_id=rule.account_id,
        dest_account_id=rule.dest_account_id,
        amount=amount,
        description=description,
        promoted_from_recurring_rule_id=rule.id,
        promoted_from_recurring_date=due_date,
    )


def _load_active_rule(conn: sqlite3.Connection, user_id: int, rule_id: int) -> RecurringRule:
    """Load a live, active rule or raise the matching not-found / inactive error."""
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        raise RecurringNotFoundError(rule_id)
    if not rule.active:
        raise InactiveRecurringError(rule_id)
    return rule


def _apply_override(
    match: RecurringOverride | None,
    rule: RecurringRule,
    *,
    amount: int,
    description: str,
    due_date: dt.date,
) -> tuple[int, str, dt.date]:
    """Merge an ``overridden`` row over the rule defaults; a ``skipped`` one cannot promote."""
    if match is None:
        return amount, description, due_date
    if match.state is OverrideState.SKIPPED:
        raise CannotPromoteSkippedError(rule.id)
    return (
        amount if match.amount_override is None else match.amount_override,
        description if match.description_override is None else match.description_override,
        due_date if match.date_override is None else match.date_override,
    )


def _promotion_values(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    due_date: dt.date,
    *,
    match: RecurringOverride | None,
    edits: PromotionEdits,
    fx: FormulaFx,
) -> tuple[int, str, dt.date]:
    """Resolve (amount, description, operation date): rule -> override -> explicit edits."""
    # Defaults start from the rule. Formula rules recompute from the
    # live source-rule state for the next_due month (ADR-0045).
    default_amount, default_description, effective_date = _apply_override(
        match,
        rule,
        amount=resolve_rule_amount(conn, user_id, rule, due_date, fx=fx),
        description=rule.default_description,
        due_date=due_date,
    )

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
    return amount, description, operation_date


def _advance_rule(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    due_date: dt.date,
    *,
    last_promoted_date: dt.date | None,
) -> None:
    """Move ``next_due`` past ``due_date`` or deactivate the rule when it ended."""
    new_next_due = advance_next_due(rule, due_date)
    if new_next_due is None:
        set_inactive(conn, user_id, rule.id)
    else:
        set_next_due(
            conn,
            user_id,
            rule.id,
            next_due=new_next_due,
            last_promoted_date=last_promoted_date,
        )


def _audit_rule_update(conn: sqlite3.Connection, user_id: int, prev: RecurringRule) -> None:
    """Audit the rule mutation against its re-read post-state."""
    updated_rule = recurring_repo.find_rule(conn, user_id, prev.id, include_deleted=True)
    audit_svc.write_audit(
        conn,
        entity_type="recurring_rule",
        entity_id=prev.id,
        operation="update",
        prev=prev,
        new=updated_rule,
        user_id=user_id,
    )


def skip_and_advance(
    conn: sqlite3.Connection,
    user_id: int,
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
    # ADR-0137: guard reads and writes share one write-locked transaction.
    with db_transaction(conn):
        rule = _load_active_rule(conn, user_id, rule_id)
        due_date = rule.next_due
        new_next_due = advance_next_due(rule, due_date)

        # Record the skip (audit emitted by the override upsert path).
        recurring_repo.upsert_override(
            conn,
            user_id,
            NewRecurringOverride(
                rule_id=rule_id,
                occurrence_date=due_date,
                state=OverrideState.SKIPPED,
            ),
        )
        _advance_rule(conn, user_id, rule, due_date, last_promoted_date=rule.last_promoted_date)
        # The skip override has served its purpose — remove it so the next
        # occurrence isn't re-skipped if ``next_due`` ever cycles back.
        recurring_repo.delete_override(conn, user_id, rule_id, due_date)
        _audit_rule_update(conn, user_id, rule)
    return new_next_due


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0038)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BatchPromoteResult:
    """Summary of a batch recurring promote-due pass.

    ``promoted_txn_ids`` carries the id of every transaction created.
    ``advanced_rule_ids`` carries the id of every rule whose ``next_due``
    was advanced (one per promotion) and ``advance_audit_ids`` the id of the
    ``audit_log`` row each advance wrote (parallel to ``promoted_txn_ids``;
    the undo targets exactly these rows). ``skipped_rule_ids`` carries the id
    of every active due rule that was intentionally not promoted (e.g. a
    skipped override on next_due).
    """

    promoted_txn_ids: tuple[int, ...]
    advanced_rule_ids: tuple[int, ...]
    skipped_rule_ids: tuple[int, ...]
    advance_audit_ids: tuple[int, ...] = ()


def batch_promote_due(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    *,
    fx: FormulaFx,
) -> BatchPromoteResult:
    """Promote every active rule whose ``next_due`` is on-or-before ``today``.

    Runs inside a single DB transaction. If any inner promote raises
    (``ValidationError`` from a formula resolving to a non-positive amount,
    etc.), the whole batch rolls back. Skipped-override rows advance via
    :func:`skip_and_advance` so the caller does not have to re-run the
    batch after a skip.
    """
    promoted: list[int] = []
    advanced: list[int] = []
    advance_audits: list[int] = []
    skipped: list[int] = []
    with db_transaction(conn):
        for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
            if rule.next_due > today:
                continue
            override = _resolve_override_for_next_due(
                recurring_repo.list_overrides(conn, user_id, rule.id), rule.next_due
            )
            if override is not None and override.state is OverrideState.SKIPPED:
                # Advance past the skip without creating a transaction.
                skip_and_advance(conn, user_id, rule.id)
                skipped.append(rule.id)
                continue
            txn = promote_recurring(conn, user_id, rule.id, PromotionEdits(), fx=fx)
            promoted.append(txn.id)
            advanced.append(rule.id)
            audit_id = audit_repo.latest_entry_id(conn, user_id, "recurring_rule", rule.id)
            if audit_id is None:
                raise LookupError(f"no audit row for recurring_rule {rule.id}")
            advance_audits.append(audit_id)
    return BatchPromoteResult(
        promoted_txn_ids=tuple(promoted),
        advanced_rule_ids=tuple(advanced),
        skipped_rule_ids=tuple(skipped),
        advance_audit_ids=tuple(advance_audits),
    )


def unpromote_override(conn: sqlite3.Connection, user_id: int, rule_id: int, txn_id: int) -> bool:
    """Clear the ``promoted_to_txn_id`` stamp a promotion left on an override; audited.

    Compare-and-set (T-Q288): only an override of ``rule_id`` still stamped with
    ``txn_id`` is touched. Returns whether one was cleared.
    """
    for prev in recurring_repo.list_overrides_all(conn, user_id, rule_id):
        if prev.promoted_to_txn_id != txn_id:
            continue
        if clear_override_promoted(conn, user_id, prev.id, txn_id=txn_id) == 0:
            return False
        updated = next(
            o for o in recurring_repo.list_overrides_all(conn, user_id, rule_id) if o.id == prev.id
        )
        audit_svc.write_audit(
            conn,
            entity_type="recurring_override",
            entity_id=prev.id,
            operation="update",
            prev=prev,
            new=updated,
            user_id=user_id,
        )
        return True
    return False


def restore_progress(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    prev: Mapping[str, object],
) -> None:
    """Restore a rule's ``next_due`` / ``last_promoted_date`` / ``active`` from a prior state.

    Audit-free by itself: ``services/recurring_undo.undo_batch`` writes the paired
    audit row in the same transaction (T-Q228).
    """
    last_promoted = prev.get("last_promoted_date")
    restore_rule_progress(
        conn,
        user_id,
        rule_id,
        next_due=dt.date.fromisoformat(str(prev["next_due"])),
        last_promoted_date=dt.date.fromisoformat(str(last_promoted)) if last_promoted else None,
        active=bool(prev["active"]),
    )


PendingKind = Literal["planned", "recurring"]


@dataclass(frozen=True, slots=True)
class PendingItem:
    """One unpromoted commitment: a persisted planned row or a virtual rule occurrence.

    ``due_date`` is where the item falls on the calendar (planned
    ``operation_date`` / occurrence ``effective_date``); ``on_date`` is where a
    consumer should place it (equal to ``due_date`` except for an overdue item
    placed on ``overdue_on``, ADR-0105 amendment 2026-11-21). ``occurrence_date``
    is the canonical schedule date (recurring only).
    """

    kind: PendingKind
    due_date: dt.date
    on_date: dt.date
    category_id: int
    direction: Direction
    account_id: int
    dest_account_id: int | None
    amount: int
    description: str
    is_overdue: bool
    planned_id: int | None
    rule_id: int | None
    occurrence_date: dt.date | None
    is_overridden: bool


@dataclass(frozen=True, slots=True)
class _Window:
    """Canonical-date window plus the overdue policy of one expansion."""

    start: dt.date | None
    end: dt.date | None
    today: dt.date | None
    include_overdue: bool
    overdue_on: dt.date | None

    def contains(self, day: dt.date) -> bool:
        """``[start, end)`` membership; dates before ``today`` also pass when overdue counts."""
        if self.end is not None and day >= self.end:
            return False
        if self.start is None or day >= self.start:
            return True
        return self.include_overdue and self.today is not None and day < self.today

    def is_overdue(self, day: dt.date) -> bool:
        return self.today is not None and day < self.today

    def placed(self, due: dt.date, day: dt.date) -> dt.date:
        """Where to put an item: its own date, or ``overdue_on`` when it is overdue."""
        if self.overdue_on is not None and self.is_overdue(day) and due < self.overdue_on:
            return self.overdue_on
        return due


def _planned_items(
    conn: sqlite3.Connection,
    user_id: int,
    win: _Window,
    kinds: Mapping[int, Direction],
    wanted: Callable[[int], bool],
) -> list[PendingItem]:
    rows = planned_repo.list_filtered(
        conn,
        user_id,
        PlannedFilter(
            date_from=None if win.include_overdue else win.start,
            date_to=win.end - dt.timedelta(days=1) if win.end is not None else None,
            promoted=False,
            live_accounts_only=True,
        ),
    )
    return [
        PendingItem(
            kind="planned",
            due_date=row.operation_date,
            on_date=win.placed(row.operation_date, row.operation_date),
            category_id=row.category_id,
            direction=kinds[row.category_id],
            account_id=row.account_id,
            dest_account_id=row.dest_account_id,
            amount=row.amount,
            description=row.description,
            is_overdue=win.is_overdue(row.operation_date),
            planned_id=row.id,
            rule_id=None,
            occurrence_date=None,
            is_overridden=False,
        )
        for row in rows
        if wanted(row.category_id) and win.contains(row.operation_date)
    ]


def _rule_occurrences(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    win: _Window,
    overrides: list[RecurringOverride],
    *,
    next_only: bool,
    fx: FormulaFx | DatesOnly,
) -> tuple[Occurrence, ...]:
    """Expand ``rule`` over the window (from ``next_due``); empty when the window misses it."""
    lo = rule.next_due
    if win.start is not None and not win.include_overdue:
        lo = max(lo, win.start)
    if next_only:
        hi = rule.next_due
    elif win.end is not None:
        hi = win.end - dt.timedelta(days=1)
    else:
        raise ValueError("an unbounded end needs next_only")
    if lo > hi:
        return ()
    return rt_expand(
        conn,
        user_id,
        rule=rule,
        overrides=overrides,
        range_start=lo,
        range_end=hi,
        fx=fx,
    )


def _rule_items(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    win: _Window,
    direction: Direction,
    *,
    overrides: list[RecurringOverride],
    dedup: frozenset[tuple[int, dt.date]],
    next_only: bool,
    fx: FormulaFx | DatesOnly,
) -> list[PendingItem]:
    occs = _rule_occurrences(conn, user_id, rule, win, overrides, next_only=next_only, fx=fx)
    return [
        PendingItem(
            kind="recurring",
            due_date=occ.effective_date,
            on_date=win.placed(occ.effective_date, occ.occurrence_date),
            category_id=rule.category_id,
            direction=direction,
            account_id=occ.account_id,
            dest_account_id=occ.dest_account_id,
            amount=occ.amount,
            description=occ.description,
            is_overdue=win.is_overdue(occ.occurrence_date),
            planned_id=None,
            rule_id=rule.id,
            occurrence_date=occ.occurrence_date,
            is_overridden=occ.is_overridden,
        )
        for occ in occs
        if (rule.id, occ.occurrence_date) not in dedup and win.contains(occ.occurrence_date)
    ]


def _all_rule_items(
    conn: sqlite3.Connection,
    user_id: int,
    win: _Window,
    kinds: Mapping[int, Direction],
    wanted: Callable[[int], bool],
    *,
    dedup: frozenset[tuple[int, dt.date]],
    next_only: bool,
    fx: FormulaFx | DatesOnly,
) -> list[PendingItem]:
    """Pending items of every wanted active rule (overrides loaded once)."""
    overrides = recurring_repo.list_pending_overrides_by_rule(conn, user_id)
    items: list[PendingItem] = []
    for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
        if wanted(rule.category_id):
            items += _rule_items(
                conn,
                user_id,
                rule,
                win,
                kinds[rule.category_id],
                overrides=overrides.get(rule.id, []),
                dedup=dedup,
                next_only=next_only,
                fx=fx,
            )
    return items


def pending_occurrences(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    fx: FormulaFx | DatesOnly,
    start: dt.date | None,
    end: dt.date | None,
    today: dt.date | None,
    include_overdue: bool,
    overdue_on: dt.date | None = None,
    directions: Collection[Direction] | None = None,
    category_ids: Collection[int] | None = None,
    next_only: bool = False,
) -> tuple[PendingItem, ...]:
    """Every unpromoted planned row and rule occurrence in ``[start, end)`` (ADR-0087, ADR-0138).

    The one "planned x active rules x overrides x linked-dedup x window" expander
    (T-Q207). ``None`` bounds are open; membership is on the canonical date.
    ``include_overdue`` adds items dated before ``today`` even below ``start`` (ADR-0105),
    placed on ``overdue_on``. Rules expand from ``next_due``; skipped and linked-row
    occurrences drop; ``next_only`` yields at most ``next_due`` per rule. ``fx`` converts
    formula amounts (T-Q286); ``DATES_ONLY`` for date-only callers.
    """
    if include_overdue and start is not None and today is None:
        raise ValueError("include_overdue with a bounded start needs today")
    kinds = {
        c.id: c.direction for c in categories_repo.list_all(conn, user_id, include_deleted=True)
    }

    def wanted(category_id: int) -> bool:
        in_ids = category_ids is None or category_id in category_ids
        return in_ids and (directions is None or kinds[category_id] in directions)

    win = _Window(start, end, today, include_overdue, overdue_on)
    dedup = linked_occurrence_keys(conn, user_id)
    items = _planned_items(conn, user_id, win, kinds, wanted)
    items += _all_rule_items(
        conn, user_id, win, kinds, wanted, dedup=dedup, next_only=next_only, fx=fx
    )
    return tuple(items)


def linked_occurrence_keys(
    conn: sqlite3.Connection, user_id: int
) -> frozenset[tuple[int, dt.date]]:
    """Return ``(rule_id, occurrence_date)`` for every unpromoted linked planned row.

    Window-independent (ADR-0087 amendment): a linked row represents its
    occurrence wherever it was re-dated, so consumers skip matching virtual
    occurrences. Unlinked rows never suppress anything.
    """
    rows = planned_repo.list_filtered(conn, user_id, PlannedFilter(promoted=False))
    return frozenset(
        (row.recurring_rule_id, row.occurrence_date)
        for row in rows
        if row.recurring_rule_id is not None and row.occurrence_date is not None
    )


__all__ = [
    "BatchPromoteResult",
    "CannotPromoteSkippedError",
    "InactiveRecurringError",
    "PendingItem",
    "PromotionEdits",
    "RecurringNotFoundError",
    "advance_next_due",
    "apply_overrides",
    "batch_promote_due",
    "create_rule",
    "deactivate_rule",
    "default_day_of_month",
    "delete_override",
    "expand",
    "find_rule",
    "first_due_on_or_after",
    "generate_occurrences",
    "linked_occurrence_keys",
    "list_overrides",
    "list_rules",
    "occurrence_in_month",
    "pending_occurrences",
    "promote_recurring",
    "resolve_rule_amount",
    "restore_progress",
    "rt_expand",
    "skip_and_advance",
    "update_rule",
    "upsert_override",
    "with_anchor_day",
]
