"""Accounts view-model values (T-Q256, Q-070).

One owner for credit-card utilisation so the card, the table row, the index
and the reconcile modal render the same precomputed numbers instead of doing
arithmetic in templates. The percentage comes from the canonical
``domain.money.percent_of`` (whole percent, floored).
"""

from __future__ import annotations

from dataclasses import dataclass

from budget_planner.domain.accounts import Account
from budget_planner.domain.money import percent_of

_FULL_BAR_PCT = 100


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
