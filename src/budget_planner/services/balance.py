"""Balance service (T-021).

Derive an account balance from ``opening_balance`` + signed sum of
non-deleted transactions. Balance is never stored (ADR-0011). This is the
single arithmetic authority for UI, forecasting, and reconciliation.

All functions are pure w.r.t. the given DB snapshot.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from budget_planner.domain.accounts import AccountStats
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)

_DEFAULT_SERIES_DAYS = 90
_SPARKLINE_MIN_POINTS = 2


class AccountNotFoundError(LookupError):
    """Raised when the account id does not exist (ignores soft-delete flag)."""


@dataclass(frozen=True, slots=True)
class SignedLeg:
    """Per-account signed effect of a single transaction."""

    account_id: int
    amount_minor: int


def signed_legs(txn: Transaction, direction: Direction) -> tuple[SignedLeg, ...]:
    """Return one or two signed legs for ``txn`` given its category direction.

    Signing rules per ADR-0008 + ADR-0009:
      * ``income`` → ``(account_id, +amount)``
      * ``expense`` → ``(account_id, -amount)``
      * ``transit`` → ``(account_id, -amount)`` + ``(dest_account_id, +amount)``
      * ``adjustment`` → ``(account_id, +amount)`` (``amount`` already signed)
    """
    if direction is Direction.INCOME:
        return (SignedLeg(account_id=txn.account_id, amount_minor=txn.amount),)
    if direction is Direction.EXPENSE:
        return (SignedLeg(account_id=txn.account_id, amount_minor=-txn.amount),)
    if direction is Direction.TRANSIT:
        if txn.dest_account_id is None:  # pragma: no cover - schema CHECK blocks it
            raise ValueError("transit transaction missing dest_account_id")
        return (
            SignedLeg(account_id=txn.account_id, amount_minor=-txn.amount),
            SignedLeg(account_id=txn.dest_account_id, amount_minor=txn.amount),
        )
    # ADJUSTMENT: pre-signed amount, pass through.
    return (SignedLeg(account_id=txn.account_id, amount_minor=txn.amount),)


def _directions_by_id(conn: sqlite3.Connection) -> dict[int, Direction]:
    """One-shot lookup of category id → direction for all live categories."""
    return {c.id: c.direction for c in categories_repo.list_all(conn, include_deleted=True)}


def _txns_affecting(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    as_of: dt.date | None = None,
) -> list[Transaction]:
    """Non-deleted transactions where source OR dest matches ``account_id``."""
    filt = TransactionFilter(account_or_dest=account_id, up_to_date=as_of)
    return transactions_repo.list_filtered(conn, filt)


def derive_balance(
    conn: sqlite3.Connection,
    account_id: int,
    as_of_date: dt.date | None = None,
) -> int:
    """Return the derived balance in minor units of the account's own currency.

    - Ignores soft-deleted transactions.
    - ``as_of_date`` is inclusive. ``None`` means "latest".
    - Transit source and destination legs both apply.
    - Adjustment amounts pass through verbatim (signed).
    """
    account = accounts_repo.find_by_id(conn, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    directions = _directions_by_id(conn)
    txns = _txns_affecting(conn, account_id, as_of=as_of_date)
    delta = 0
    for txn in txns:
        direction = directions[txn.category_id]
        for leg in signed_legs(txn, direction):
            if leg.account_id == account_id:
                delta += leg.amount_minor
    return account.opening_balance + delta


def _mean(values: list[int]) -> int:
    """Mean rounded to the nearest integer with banker's rounding; 0 on empty."""
    if not values:
        return 0
    total = Decimal(sum(values))
    count = Decimal(len(values))
    quantised = (total / count).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(quantised)


def account_stats(conn: sqlite3.Connection, account_id: int) -> AccountStats:
    """Current balance + descriptive stats. Pure; no caching.

    Averages consider only ``income`` / ``expense`` legs. Transit and
    adjustment legs contribute to ``txn_count`` and ``last_txn_date`` but
    not to the averages.
    """
    account = accounts_repo.find_by_id(conn, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    directions = _directions_by_id(conn)
    txns = _txns_affecting(conn, account_id)

    inflows: list[int] = []
    outflows: list[int] = []
    legs_count = 0
    last_date: dt.date | None = None
    delta = 0
    for txn in txns:
        direction = directions[txn.category_id]
        for leg in signed_legs(txn, direction):
            if leg.account_id != account_id:
                continue
            legs_count += 1
            delta += leg.amount_minor
            if last_date is None or txn.operation_date > last_date:
                last_date = txn.operation_date
            if direction is Direction.INCOME:
                inflows.append(leg.amount_minor)
            elif direction is Direction.EXPENSE:
                outflows.append(abs(leg.amount_minor))

    balance_value = account.opening_balance + delta
    return AccountStats(
        account_id=account_id,
        balance=balance_value,
        base_balance=balance_value,
        txn_count=legs_count,
        last_txn_date=last_date.isoformat() if last_date is not None else None,
        avg_inflow_minor=_mean(inflows),
        avg_outflow_minor=_mean(outflows),
    )


def sparkline_points(
    values: list[int],
    *,
    width: int = 120,
    height: int = 32,
) -> str:
    """Return an SVG ``points="x,y x,y …"`` string for a sparkline polyline.

    Pure. Empty / single-point input returns ``""``. A flat series (min==max)
    renders a centred horizontal line to avoid a NaN mapping.
    """
    if len(values) < _SPARKLINE_MIN_POINTS:
        return ""
    vmin = min(values)
    vmax = max(values)
    span = vmax - vmin
    denom = len(values) - 1
    parts: list[str] = []
    for i, v in enumerate(values):
        x = round(i * width / denom, 2)
        y = height / 2 if span == 0 else round(height - ((v - vmin) / span) * height, 2)
        parts.append(f"{x},{y}")
    return " ".join(parts)


def balance_series(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    days: int = _DEFAULT_SERIES_DAYS,
    today: dt.date | None = None,
) -> list[tuple[dt.date, int]]:
    """Return a daily (date, balance) series for the last ``days`` days.

    The series is oldest → newest and inclusive on both ends — it contains
    ``days`` points, with the last entry equal to ``today``'s balance.

    This is a shim: it calls :func:`derive_balance` once per day. It is
    O(days * txns); fine for a card and well below any realistic account's
    history, but a Phase 7 task should replace it with a single SQL window.
    """
    if days < 1:
        return []
    end = today if today is not None else dt.date.today()  # noqa: DTZ011
    start = end - dt.timedelta(days=days - 1)
    out: list[tuple[dt.date, int]] = []
    current = start
    while current <= end:
        out.append((current, derive_balance(conn, account_id, as_of_date=current)))
        current = current + dt.timedelta(days=1)
    return out


__all__ = [
    "AccountNotFoundError",
    "SignedLeg",
    "account_stats",
    "balance_series",
    "derive_balance",
    "signed_legs",
    "sparkline_points",
]
