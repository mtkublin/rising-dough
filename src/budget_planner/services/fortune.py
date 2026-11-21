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


def compute_fortune(
    conn: sqlite3.Connection, user_id: int, converter: fx_service.FxConverter
) -> FortuneTotals:
    """Return the Assets / Liabilities / Net split over live accounts (ADR-0139, Q-009).

    Per-currency buckets stay native; ``*_base`` fields sum each account converted
    at the converter's latest cached rate (a missing rate raises ``FxUnavailableError``).
    """
    assets_by_ccy: dict[str, int] = {}
    liabilities_by_ccy: dict[str, int] = {}
    net_by_ccy: dict[str, int] = {}
    assets_base = 0
    liabilities_base = 0
    net_base = 0
    for account in accounts_repo.list_all(conn, user_id):
        bal = balance_service.derive_balance(conn, user_id, account.id)
        ccy = account.currency
        if account.is_liability:
            liabilities_by_ccy[ccy] = liabilities_by_ccy.get(ccy, 0) + abs(bal)
            liabilities_base += converter.to_base(abs(bal), ccy)
        else:
            assets_by_ccy[ccy] = assets_by_ccy.get(ccy, 0) + bal
            assets_base += converter.to_base(bal, ccy)
        net_by_ccy[ccy] = net_by_ccy.get(ccy, 0) + bal
        net_base += converter.to_base(bal, ccy)
    return FortuneTotals(
        assets_by_ccy=assets_by_ccy,
        liabilities_by_ccy=liabilities_by_ccy,
        net_by_ccy=net_by_ccy,
        assets_base=assets_base,
        liabilities_base=liabilities_base,
        net_base=net_base,
    )


__all__ = ["FortuneTotals", "compute_fortune"]
