"""Shared aggregates: the one owner of category sums and means (Q-008, Q-010, T-Q227).

``mean_minor`` is the single half-even mean. Three "average" definitions use it; each is
named here and documented once so a reader sees all of them in one place (OQ-7, default
taken 2026-11-21, pending operator confirmation: the definitions stay as they are):

* **Per active month** (``budget.month_summary`` ``avg_overall``): category total divided by
  the number of distinct months in which the category had an expense.
* **Per elapsed month of the year** (``budget.month_summary`` ``avg_year``): year-to-date
  total divided by the months elapsed in the year, including empty ones.
* **Trailing twelve months** (``analytics`` ``_twelve_month_averages``): window total divided
  by a fixed 12, including empty months.
* **Per transaction** (``balance`` account stats ``avg_inflow_minor`` and ``avg_outflow_minor``):
  total divided by the number of income or expense legs, not by months.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable

from budget_planner.domain.money import HALF_EVEN, round_div
from budget_planner.domain.transactions import Transaction


def mean_minor(total_minor: int, count: int) -> int:
    """Mean of ``total_minor`` over ``count`` items, half-even; 0 when ``count <= 0``."""
    if count <= 0:
        return 0
    return round_div(total_minor, count, mode=HALF_EVEN)


def sum_by_category(
    txns: Iterable[Transaction], to_base: Callable[[Transaction], int]
) -> dict[int, int]:
    """Sum ``to_base(txn)`` per ``category_id`` (base-currency minor units)."""
    out: dict[int, int] = defaultdict(int)
    for txn in txns:
        out[txn.category_id] += to_base(txn)
    return dict(out)


__all__ = ["mean_minor", "sum_by_category"]
