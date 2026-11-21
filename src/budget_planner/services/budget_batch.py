"""Batch budget reads: resolve and commit many (category, month) pairs at once (T-Q234).

``budget.resolve_budget`` and ``budget.committed_by_category`` issue queries per call;
a forecast loop over categories x months turned that into thousands of statements.
These variants load once and answer in memory, with the same semantics.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from budget_planner.domain.enums import Direction
from budget_planner.repositories import budgets as budgets_repo
from budget_planner.services import recurring as recurring_svc
from budget_planner.services.budget import planned_base_amounts


def budget_resolver(
    conn: sqlite3.Connection, user_id: int
) -> Callable[[int, int, int], int | None]:
    """Return ``resolve(category_id, year, month)`` backed by three queries in total.

    Same one-off, recurring, default null-coalesce as ``budget.resolve_budget`` (zero is a
    valid value), with the three tiers loaded once.
    """
    one_off = {
        (o.category_id, o.year, o.month): o.amount for o in budgets_repo.list_one_off(conn, user_id)
    }
    recurring = {
        (r.category_id, r.month): r.amount for r in budgets_repo.list_recurring(conn, user_id)
    }
    defaults = {d.category_id: d.amount for d in budgets_repo.list_defaults(conn, user_id)}

    def resolve(category_id: int, year: int, month: int) -> int | None:
        hit = one_off.get((category_id, year, month))
        if hit is None:
            hit = recurring.get((category_id, month))
        if hit is None:
            hit = defaults.get(category_id)
        return hit

    return resolve


@dataclass(frozen=True, slots=True)
class CommitWindow:
    """One half-open ``[start, end)`` window for :func:`committed_by_category_windows`."""

    start: dt.date
    end: dt.date
    include_overdue: bool = False


def _in_window(window: CommitWindow, canonical: dt.date, today: dt.date) -> bool:
    if window.end <= window.start:
        return False
    return window.start <= canonical < window.end or (window.include_overdue and canonical < today)


def committed_by_category_windows(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    windows: Sequence[CommitWindow],
    today: dt.date,
    base_currency: str | None = None,
) -> list[dict[int, int]]:
    """``budget.committed_by_category`` for many windows with ONE expansion.

    Pending items are expanded once over the union of the windows and bucketed by
    canonical date, so the query count does not grow with the number of windows.
    An item belongs to a window when its canonical date is in ``[start, end)`` or,
    for ``include_overdue`` windows, when it is dated before ``today`` (ADR-0105).
    """
    live = [w for w in windows if w.end > w.start]
    out: list[dict[int, int]] = [{} for _ in windows]
    if not live:
        return out
    base_of = planned_base_amounts(conn, user_id, today=today, base_currency=base_currency)
    items = recurring_svc.pending_occurrences(
        conn,
        user_id,
        start=min(w.start for w in live),
        end=max(w.end for w in live),
        today=today,
        include_overdue=any(w.include_overdue for w in live),
        directions=(Direction.EXPENSE,),
    )
    for item in items:
        canonical = item.due_date if item.occurrence_date is None else item.occurrence_date
        amount = base_of(item.account_id, item.amount)
        for idx in _matching(windows, canonical, today):
            out[idx][item.category_id] = out[idx].get(item.category_id, 0) + amount
    return out


def _matching(windows: Sequence[CommitWindow], canonical: dt.date, today: dt.date) -> list[int]:
    """Indexes of the windows that contain an item with this canonical date."""
    return [i for i, w in enumerate(windows) if _in_window(w, canonical, today)]


__all__ = ["CommitWindow", "budget_resolver", "committed_by_category_windows"]
