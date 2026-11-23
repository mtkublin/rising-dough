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
from enum import StrEnum

from budget_planner.domain.enums import Cadence, Direction, months_per_cadence
from budget_planner.domain.money import divide_minor_units, format_money
from budget_planner.domain.transactions import signed_legs
from budget_planner.services.fx import FxUnavailableError

# (amount_minor, operation_date, from_ccy) -> base-currency minor units
Converter = Callable[[int, dt.date, str], int]


def signed_effect(amount_minor: int, direction: Direction) -> int:
    """Signed contribution of one transaction to a day's net (0 for transit)."""
    if direction is Direction.TRANSIT:
        return 0
    return signed_legs(direction, amount_minor, 0, None)[0].amount_minor


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


def actual_day_nets(
    rows: Iterable[tuple[dt.date, int, Direction | None, str]],
    base_of: Converter,
) -> dict[str, int | None]:
    """Per-day net with ISO-date keys for the Ledger Actual view (T-D48).

    A day whose FX rate is unavailable maps to ``None`` so the header omits a wrong figure.
    """
    items = list(rows)
    out: dict[str, int | None] = {}
    for day in {i[0] for i in items}:
        try:
            out[day.isoformat()] = day_nets([i for i in items if i[0] == day], base_of)[day]
        except FxUnavailableError:
            out[day.isoformat()] = None
    return out


@dataclass(frozen=True)
class RecurringTotals:
    """Monthly-equivalent in/out for the Recurring strip (magnitudes, minor units)."""

    monthly_in_minor: int
    monthly_out_minor: int
    monthly_in_display: str
    monthly_out_display: str
    rule_count: int = 0
    next_due: dt.date | None = None
    net_minor: int = 0  # monthly_in_minor - monthly_out_minor (signed, like the planned net)


@dataclass(frozen=True)
class PlannedTotals:
    """Pending planned count and direction-signed net for the Planned strip."""

    count: int
    net_minor: int
    net_display: str
    overdue_count: int = 0
    due_today_count: int = 0


class PlannedStatusKind(StrEnum):
    """Where a planned row sits relative to the user's local today (T-UR34c, ADR-0147 section 3)."""

    IN_DAYS = "in_days"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


@dataclass(frozen=True)
class PlannedStatus:
    """Structured planned-row status; ``days`` is the non-negative distance to today."""

    kind: PlannedStatusKind
    days: int


class DeltaDirection(StrEnum):
    """Direction of an override amount against the rule amount (magnitudes only, ADR-0008)."""

    UP = "up"
    DOWN = "down"
    SAME = "same"


@dataclass(frozen=True)
class OverrideDelta:
    """Absolute minor-unit difference between an override and the rule amount, plus direction."""

    magnitude_minor: int
    direction: DeltaDirection


def planned_status(due: dt.date, today: dt.date) -> PlannedStatus:
    """Classify ``due`` against ``today``: ``in N days``, ``due today`` or ``overdue N days``."""
    days = (due - today).days
    if days > 0:
        return PlannedStatus(PlannedStatusKind.IN_DAYS, days)
    if days == 0:
        return PlannedStatus(PlannedStatusKind.DUE_TODAY, 0)
    return PlannedStatus(PlannedStatusKind.OVERDUE, -days)


def override_delta(rule_amount_minor: int, override_amount_minor: int) -> OverrideDelta:
    """Override minus rule amount as an absolute amount and a direction (both positive units)."""
    diff = override_amount_minor - rule_amount_minor
    if diff == 0:
        return OverrideDelta(0, DeltaDirection.SAME)
    return OverrideDelta(abs(diff), DeltaDirection.UP if diff > 0 else DeltaDirection.DOWN)


def spent_minor(
    rows: Iterable[tuple[dt.date, int, Direction | None, str]], base_of: Converter
) -> int | None:
    """Base-currency total of the expense rows (a positive magnitude), via ``day_nets``.

    ``None`` when a rate is unavailable, so the hero omits a wrong figure.
    """
    expenses = [r for r in rows if r[2] is Direction.EXPENSE]
    total: int | None
    try:
        total = -sum(day_nets(expenses, base_of).values())
    except FxUnavailableError:
        total = None
    return total


def _int_field(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    return value if isinstance(value, int) else 0


def _direction_of(row: Mapping[str, object]) -> Direction | None:
    direction = getattr(row.get("category"), "direction", None)
    return direction if isinstance(direction, Direction) else None


def _date_field(row: Mapping[str, object], key: str) -> dt.date:
    value = row.get(key)
    if not isinstance(value, dt.date):
        raise ValueError(f"ledger strip row has no {key} date")
    return value


def _ccy_field(row: Mapping[str, object], base: str) -> str:
    value = row.get("currency")
    return value if isinstance(value, str) and value else base


def recurring_monthly_totals(
    rows: Iterable[Mapping[str, object]], currency: str, base_of: Converter
) -> RecurringTotals:
    """Roll active recurring rows up to monthly-equivalent in/out (ADR-0056 section 4).

    Each row carries ``effective_amount_minor``, ``cadence`` and a ``category``
    with a direction. The monthly amount is signed via ``signed_effect``
    (ADR-0008): positives are income (in), negatives expense (out, reported as a
    magnitude). Rows without a direction are ignored. Each monthly amount is
    converted from its account currency to ``currency`` (the base) at the rate
    on the rule's ``next_due`` via ``base_of`` (ADR-0006, ADR-0139); a missing
    rate raises ``FxUnavailableError``.
    """
    monthly_in = 0
    monthly_out = 0
    count = 0
    dues: list[dt.date] = []
    for row in rows:
        cadence = Cadence(str(row.get("cadence")))  # unknown or missing cadence raises
        count += 1
        due = row.get("next_due")
        if isinstance(due, dt.date):
            dues.append(due)
        direction = _direction_of(row)
        if direction is None:
            continue
        amount = divide_minor_units(
            _int_field(row, "effective_amount_minor"), months_per_cadence(cadence)
        )
        effect = base_of(
            signed_effect(amount, direction),
            _date_field(row, "next_due"),
            _ccy_field(row, currency),
        )
        if effect >= 0:
            monthly_in += effect
        else:
            monthly_out -= effect
    return RecurringTotals(
        monthly_in_minor=monthly_in,
        monthly_out_minor=monthly_out,
        monthly_in_display=format_money(monthly_in, currency),
        monthly_out_display=format_money(monthly_out, currency),
        rule_count=count,
        next_due=min(dues) if dues else None,
        net_minor=monthly_in - monthly_out,
    )


def planned_totals(
    rows: Iterable[Mapping[str, object]],
    currency: str,
    base_of: Converter,
    today: dt.date | None = None,
) -> PlannedTotals:
    """Count pending planned rows and sum their direction-signed net (ADR-0008).

    Rows carry ``amount_minor``, ``is_promoted`` and a ``category`` with a
    direction. Promoted rows are already in the ledger and are excluded from
    both the count and the net; rows without a direction add nothing. Each
    amount is converted to ``currency`` (the base) at its ``operation_date`` via
    ``base_of`` (ADR-0006, ADR-0139); a missing rate raises ``FxUnavailableError``.
    With ``today`` (the user's local date) the pending rows dated before it count as
    overdue and those dated on it as due today (T-UR34c).
    """
    pending = [row for row in rows if not row.get("is_promoted")]
    net = 0
    for row in pending:
        direction = _direction_of(row)
        if direction is not None:
            net += base_of(
                signed_effect(_int_field(row, "amount_minor"), direction),
                _date_field(row, "operation_date"),
                _ccy_field(row, currency),
            )
    dated = [_date_field(row, "operation_date") for row in pending] if today else []
    return PlannedTotals(
        count=len(pending),
        net_minor=net,
        net_display=format_money(net, currency),
        overdue_count=sum(1 for d in dated if today and d < today),
        due_today_count=sum(1 for d in dated if d == today),
    )


__all__ = [
    "Converter",
    "DeltaDirection",
    "OverrideDelta",
    "PlannedStatus",
    "PlannedStatusKind",
    "PlannedTotals",
    "RecurringTotals",
    "actual_day_nets",
    "day_nets",
    "override_delta",
    "planned_status",
    "planned_totals",
    "recurring_monthly_totals",
    "signed_effect",
    "spent_minor",
]
