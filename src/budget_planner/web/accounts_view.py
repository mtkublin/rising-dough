"""Accounts view-model values (T-Q256, Q-070).

One owner for credit-card utilisation so the card, the table row, the index
and the reconcile modal render the same precomputed numbers instead of doing
arithmetic in templates. The percentage comes from the canonical
``domain.money.percent_of`` (whole percent, floored).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from budget_planner.domain.accounts import Account
from budget_planner.domain.money import percent_of
from budget_planner.services.balance import sparkline_points

_FULL_BAR_PCT = 100
_SPARKLINE_WIDTH = 120
_SPARKLINE_HEIGHT = 32


@dataclass(frozen=True)
class CreditUtilisation:
    """Utilisation of a credit limit. Amounts are minor units, percents whole."""

    limit_minor: int
    used_minor: int
    available_minor: int
    over_limit_minor: int
    used_pct: int
    bar_pct: int


def credit_utilisation(account: Account, balance_minor: int) -> CreditUtilisation | None:
    """Utilisation for a liability with a positive credit limit, else ``None``.

    ``balance_minor`` is the derived balance (negative when money is owed).
    """
    limit = account.credit_limit_minor or 0
    if not account.is_liability or limit <= 0:
        return None
    used = max(-balance_minor, 0)
    used_pct = percent_of(used, limit)
    return CreditUtilisation(
        limit_minor=limit,
        used_minor=used,
        available_minor=max(limit - used, 0),
        over_limit_minor=max(used - limit, 0),
        used_pct=used_pct,
        bar_pct=min(used_pct, _FULL_BAR_PCT),
    )


def sparkline_fields(series: list[tuple[date, int]]) -> dict[str, object]:
    """Precomputed sparkline template values for one balance series (no template math)."""
    values = [v for _, v in series]
    points = sparkline_points(values, width=_SPARKLINE_WIDTH, height=_SPARKLINE_HEIGHT)
    area = (
        f"0,{_SPARKLINE_HEIGHT} {points} {_SPARKLINE_WIDTH},{_SPARKLINE_HEIGHT}" if points else ""
    )
    return {
        "sparkline_points": points,
        "sparkline_values": values,
        "sparkline_area_points": area,
        "sparkline_width": _SPARKLINE_WIDTH,
        "sparkline_height": _SPARKLINE_HEIGHT,
    }
