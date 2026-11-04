"""Ledger Actual-view totals (T-D48, ADR-0008).

Per-day net for the Ledger day-group header. The sign of each row's
contribution follows ADR-0008: ``income`` is ``+amount``, ``expense`` is
``-amount``, ``adjustment`` (reconciliation) is stored *already signed* so it
passes through unchanged, and ``transit`` nets to zero and is excluded.
Amounts are converted to the base currency per row (ADR-0006) so a day that
spans accounts in different currencies is summed in one unit.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable

from budget_planner.domain.enums import Direction

# (amount_minor, operation_date, from_ccy) -> base-currency minor units
Converter = Callable[[int, dt.date, str], int]


def signed_effect(amount_minor: int, direction: Direction) -> int:
    """Signed contribution of one transaction to a day's net (0 for transit)."""
    if direction is Direction.INCOME:
        return amount_minor
    if direction is Direction.EXPENSE:
        return -amount_minor
    if direction is Direction.ADJUSTMENT:
        return amount_minor  # pre-signed (ADR-0008)
    return 0


def day_nets(
    rows: Iterable[tuple[dt.date, int, Direction | None, str]],
    convert: Converter,
) -> dict[dt.date, int]:
    """Sum signed base-currency effects per operation date.

    ``rows`` are ``(operation_date, amount_minor, direction, currency)``.
    Rows without a category direction are ignored.
    """
    out: dict[dt.date, int] = {}
    for day, amount, direction, ccy in rows:
        if direction is None:
            continue
        effect = signed_effect(amount, direction)
        if effect == 0:
            out.setdefault(day, 0)
            continue
        out[day] = out.get(day, 0) + convert(effect, day, ccy)
    return out


__all__ = ["Converter", "day_nets", "signed_effect"]
