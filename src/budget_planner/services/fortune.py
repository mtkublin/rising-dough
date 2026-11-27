"""Fortune aggregation — Assets / Liabilities / Net worth split.

See ADR-0024. ``derive_balance`` + ``signed_legs`` arithmetic (ADR-0008) is
untouched; this module is a pure reporting composition that groups per-account
balances by ``is_liability``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import balance as balance_service, fx as fx_service


@dataclass(frozen=True, slots=True)
class FortuneTotals:
    """Per-currency buckets + base-currency selections (ADR-0024)."""

    assets_by_ccy: dict[str, int]
    liabilities_by_ccy: dict[str, int]
    net_by_ccy: dict[str, int]
    assets_base: int
    liabilities_base: int
    net_base: int
    unconverted_ccys: tuple[str, ...] = ()


def _to_base_pair(
    converter: fx_service.FxConverter, bal: int, ccy: str, *, skip: bool
) -> tuple[int, int] | None:
    """``(balance, abs balance)`` in base; ``None`` when the rate is missing and ``skip``."""
    try:
        return converter.to_base(bal, ccy), converter.to_base(abs(bal), ccy)
    except fx_service.FxUnavailableError:
        if skip:
            return None
        raise


def compute_fortune(
    conn: sqlite3.Connection,
    user_id: int,
    converter: fx_service.FxConverter,
    *,
    skip_unconvertible: bool = False,
) -> FortuneTotals:
    """Return the Assets / Liabilities / Net split over live accounts (ADR-0139, Q-009).

    Per-currency buckets stay native; ``*_base`` fields sum each account at the latest cached
    rate; a missing rate raises ``FxUnavailableError`` unless ``skip_unconvertible`` (T-UR69)
    leaves the account out and lists its currency in ``unconverted_ccys``.
    """
    assets_by_ccy: dict[str, int] = {}
    liabilities_by_ccy: dict[str, int] = {}
    net_by_ccy: dict[str, int] = {}
    assets_base = 0
    liabilities_base = 0
    net_base = 0
    unconverted: set[str] = set()
    accounts = accounts_repo.list_all(conn, user_id)
    balances = balance_service.derive_balances(conn, user_id, accounts)
    for account in accounts:
        bal = balances[account.id]
        ccy = account.currency
        if account.is_liability:
            liabilities_by_ccy[ccy] = liabilities_by_ccy.get(ccy, 0) + abs(bal)
        else:
            assets_by_ccy[ccy] = assets_by_ccy.get(ccy, 0) + bal
        net_by_ccy[ccy] = net_by_ccy.get(ccy, 0) + bal
        converted = _to_base_pair(converter, bal, ccy, skip=skip_unconvertible)
        if converted is None:
            unconverted.add(ccy)
            continue
        in_base, owed_base = converted
        if account.is_liability:
            liabilities_base += owed_base
        else:
            assets_base += in_base
        net_base += in_base
    return FortuneTotals(
        assets_by_ccy=assets_by_ccy,
        liabilities_by_ccy=liabilities_by_ccy,
        net_by_ccy=net_by_ccy,
        assets_base=assets_base,
        liabilities_base=liabilities_base,
        net_base=net_base,
        unconverted_ccys=tuple(sorted(unconverted)),
    )


__all__ = ["FortuneTotals", "compute_fortune"]
