"""Planned log service (T-023 / T-119).

Returns persisted ``planned_transactions`` rows only. The virtual-recurring
union was dropped in T-119 (ADR-0038): recurring rows live in their own
``recurring_rules`` lifecycle (``next_due`` / promote / skip-and-advance)
and surface via ``services.upcoming`` + ``services.income`` instead.

Also performs the manual planned → actual promotion flow (ADR-0012) in a
single DB transaction.
"""

from __future__ import annotations

import calendar
import datetime as dt
import sqlite3
from dataclasses import dataclass
from typing import Literal

from budget_planner.domain.planned import PlannedFilter, PlannedTransaction
from budget_planner.domain.transactions import NewTransaction, Transaction
from budget_planner.repositories import (
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services._promotion import (
    UnsupportedDirectionError,
    ValidationError,
    validate_promotion as _shared_validate_promotion,
)

# After T-119 (ADR-0038) planned rows are always persisted. The literal is
# kept as a single-value alias so templates and callers can keep reading
# ``view.kind`` without a rename.
PlannedKind = Literal["persisted"]


@dataclass(frozen=True, slots=True)
class PlannedView:
    kind: PlannedKind
    operation_date: dt.date
    account_id: int
    dest_account_id: int | None
    category_id: int
    amount_minor: int
    description: str
    persisted_id: int | None
    recurring_rule_id: int | None
    occurrence_date: dt.date | None
    is_overridden: bool
    is_promoted: bool


@dataclass(frozen=True, slots=True)
class PromotionEdits:
    operation_date: dt.date | None = None
    amount_minor: int | None = None
    description: str | None = None


class PlannedNotFoundError(LookupError):
    """Raised when the planned_id does not exist."""


class AlreadyPromotedError(RuntimeError):
    """Raised when the planned row has already been promoted."""


class CannotPromoteDeletedError(RuntimeError):
    """Raised when attempting to promote a soft-deleted planned row."""


# ``UnsupportedDirectionError`` + ``ValidationError`` are re-exported from the
# shared ``services._promotion`` module (T-118). Both historical identifiers
# resolve to the same classes so existing ``services.planned.ValidationError``
# imports keep working.


# ---------------------------------------------------------------------------
# list_planned
# ---------------------------------------------------------------------------
def _default_window(filters: PlannedFilter) -> tuple[dt.date, dt.date]:
    """Fill in a window if filters don't specify one — defaults to the current month."""
    today = dt.date.today()  # noqa: DTZ011 - naive date, routers inject when needed
    first = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    last = today.replace(day=last_day)
    date_from = filters.date_from or first
    date_to = filters.date_to or last
    return date_from, date_to


def _persisted_to_view(row: PlannedTransaction) -> PlannedView:
    return PlannedView(
        kind="persisted",
        operation_date=row.operation_date,
        account_id=row.account_id,
        dest_account_id=row.dest_account_id,
        category_id=row.category_id,
        amount_minor=row.amount,
        description=row.description,
        persisted_id=row.id,
        recurring_rule_id=row.recurring_rule_id,
        occurrence_date=row.occurrence_date,
        is_overridden=False,
        is_promoted=row.promoted_to_txn_id is not None,
    )


def list_planned(
    conn: sqlite3.Connection,
    filters: PlannedFilter,
) -> tuple[PlannedView, ...]:
    """Return persisted planned rows filtered + sorted.

    After T-119 (ADR-0038) this surface no longer unions virtual recurring
    occurrences. The forecast service continues to call
    ``services.recurring.expand`` directly for its horizon projection;
    Overview Upcoming composes planned + recurring through
    ``services.upcoming.list_upcoming``.
    """
    # ``_default_window`` honours the historical "no window → current month"
    # fallback so callers that omit date_from / date_to keep their previous
    # output shape even though the virtual branch is gone.
    date_from, date_to = _default_window(filters)
    effective_filters = PlannedFilter(
        date_from=filters.date_from or date_from,
        date_to=filters.date_to or date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        directions=filters.directions,
        recurring_rule_id=filters.recurring_rule_id,
        promoted=filters.promoted,
        limit=filters.limit,
        offset=filters.offset,
    )
    persisted_rows = planned_repo.list_filtered(conn, effective_filters)
    views = [_persisted_to_view(row) for row in persisted_rows]
    views.sort(key=lambda v: (v.operation_date, v.persisted_id or 0))
    return tuple(views)


# ---------------------------------------------------------------------------
# promote_to_actual
# ---------------------------------------------------------------------------
def promote_to_actual(
    conn: sqlite3.Connection,
    planned_id: int,
    edits: PromotionEdits,
) -> Transaction:
    """Insert a transactions row linked to ``planned_id`` and stamp the planned row.

    Both mutations and their audit entries happen in a single DB transaction.
    Raises:
      ``PlannedNotFoundError``, ``AlreadyPromotedError``,
      ``CannotPromoteDeletedError``, ``UnsupportedDirectionError``,
      ``ValidationError``.
    """
    row = planned_repo.find_by_id(conn, planned_id, include_deleted=True)
    if row is None:
        raise PlannedNotFoundError(planned_id)
    if row.deleted_at is not None:
        raise CannotPromoteDeletedError(planned_id)
    if row.promoted_to_txn_id is not None:
        raise AlreadyPromotedError(planned_id)

    category = categories_repo.find_by_id(conn, row.category_id, include_deleted=True)
    if category is None:  # pragma: no cover - FK guarantees existence
        raise ValidationError(f"category {row.category_id} not found")
    operation_date = edits.operation_date or row.operation_date
    amount = edits.amount_minor if edits.amount_minor is not None else row.amount
    description = edits.description if edits.description is not None else row.description
    _shared_validate_promotion(
        conn,
        direction=category.direction,
        account_id=row.account_id,
        dest_account_id=row.dest_account_id,
        amount=amount,
    )

    new_txn = NewTransaction(
        operation_date=operation_date,
        category_id=row.category_id,
        account_id=row.account_id,
        dest_account_id=row.dest_account_id,
        amount=amount,
        description=description,
        promoted_from_planned_id=planned_id,
    )

    with db_transaction(conn):
        txn = transactions_repo.create(conn, new_txn)
        planned_repo.stamp_promotion(conn, planned_id, txn.id)
    return txn


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0012)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BatchPromoteResult:
    """Summary of a batch planned promote-due pass.

    ``promoted_txn_ids`` carries the id of every transaction created.
    ``promoted_planned_ids`` carries the id of every planned row that was
    stamped with the matching ``promoted_to_txn_id``.
    """

    promoted_txn_ids: tuple[int, ...]
    promoted_planned_ids: tuple[int, ...]


def batch_promote_due(
    conn: sqlite3.Connection,
    today: dt.date,
) -> BatchPromoteResult:
    """Promote every unpromoted planned row with ``operation_date <= today``.

    Runs inside a single DB transaction; any inner failure rolls everything
    back. Soft-deleted rows are excluded by the repo filter.
    """
    filters = PlannedFilter(
        date_to=today,
        promoted=False,
    )
    due_rows = planned_repo.list_filtered(conn, filters)
    promoted_txns: list[int] = []
    promoted_planned: list[int] = []
    with db_transaction(conn):
        for row in due_rows:
            txn = promote_to_actual(conn, row.id, PromotionEdits())
            promoted_txns.append(txn.id)
            promoted_planned.append(row.id)
    return BatchPromoteResult(
        promoted_txn_ids=tuple(promoted_txns),
        promoted_planned_ids=tuple(promoted_planned),
    )


__all__ = [
    "AlreadyPromotedError",
    "BatchPromoteResult",
    "CannotPromoteDeletedError",
    "PlannedKind",
    "PlannedNotFoundError",
    "PlannedView",
    "PromotionEdits",
    "UnsupportedDirectionError",
    "ValidationError",
    "batch_promote_due",
    "list_planned",
    "promote_to_actual",
]
