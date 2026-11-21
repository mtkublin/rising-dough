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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from budget_planner.domain.enums import Cadence, Direction, months_per_cadence
from budget_planner.domain.money import divide_minor_units, format_money

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
    base_of: Converter,
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
        out[day] = out.get(day, 0) + base_of(effect, day, ccy)
    return out


@dataclass(frozen=True)
class RecurringTotals:
    """Monthly-equivalent in/out for the Recurring strip (magnitudes, minor units)."""

    monthly_in_minor: int
    monthly_out_minor: int
    monthly_in_display: str
    monthly_out_display: str


@dataclass(frozen=True)
class PlannedTotals:
    """Pending planned count and direction-signed net for the Planned strip."""

    count: int
    net_minor: int
    net_display: str


def _int_field(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    return value if isinstance(value, int) else 0


def _direction_of(row: Mapping[str, object]) -> Direction | None:
    direction = getattr(row.get("category"), "direction", None)
    return direction if isinstance(direction, Direction) else None


def recurring_monthly_totals(
    rows: Iterable[Mapping[str, object]], currency: str
) -> RecurringTotals:
    """Roll active recurring rows up to monthly-equivalent in/out (ADR-0056 section 4).

    Each row carries ``effective_amount_minor``, ``cadence`` and a ``category``
    with a direction. The monthly amount is signed via ``signed_effect``
    (ADR-0008): positives are income (in), negatives expense (out, reported as a
    magnitude). Rows without a direction are ignored.
    """
    monthly_in = 0
    monthly_out = 0
    for row in rows:
        cadence = Cadence(str(row.get("cadence")))  # unknown or missing cadence raises
        direction = _direction_of(row)
        if direction is None:
            continue
        amount = divide_minor_units(
            _int_field(row, "effective_amount_minor"), months_per_cadence(cadence)
        )
        effect = signed_effect(amount, direction)
        if effect >= 0:
            monthly_in += effect
        else:
            monthly_out -= effect
    return RecurringTotals(
        monthly_in_minor=monthly_in,
        monthly_out_minor=monthly_out,
        monthly_in_display=format_money(monthly_in, currency),
        monthly_out_display=format_money(monthly_out, currency),
    )


def planned_totals(rows: Iterable[Mapping[str, object]], currency: str) -> PlannedTotals:
    """Count pending planned rows and sum their direction-signed net (ADR-0008).

    Rows carry ``amount_minor``, ``is_promoted`` and a ``category`` with a
    direction. Promoted rows are already in the ledger and are excluded from
    both the count and the net; rows without a direction add nothing.
    """
    pending = [row for row in rows if not row.get("is_promoted")]
    net = 0
    for row in pending:
        direction = _direction_of(row)
        if direction is not None:
            net += signed_effect(_int_field(row, "amount_minor"), direction)
    return PlannedTotals(count=len(pending), net_minor=net, net_display=format_money(net, currency))


__all__ = [
    "Converter",
    "PlannedTotals",
    "RecurringTotals",
    "day_nets",
    "planned_totals",
    "recurring_monthly_totals",
    "signed_effect",
]
