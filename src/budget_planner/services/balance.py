"""Balance service (T-021).

Derive an account balance from ``opening_balance`` + signed sum of
non-deleted transactions. Balance is never stored (ADR-0011). This is the
single arithmetic authority for UI, forecasting, and reconciliation.

All functions are pure w.r.t. the given DB snapshot.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from budget_planner.domain.accounts import Account, AccountStats
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import mean_minor
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


def _directions_by_id(conn: sqlite3.Connection, user_id: int) -> dict[int, Direction]:
    """One-shot lookup of category id → direction for all live categories."""
    return {
        c.id: c.direction for c in categories_repo.list_all(conn, user_id, include_deleted=True)
    }


def _txns_affecting(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    *,
    as_of: dt.date | None = None,
) -> list[Transaction]:
    """Non-deleted transactions where source OR dest matches ``account_id``."""
    filt = TransactionFilter(account_or_dest=account_id, up_to_date=as_of)
    return transactions_repo.list_filtered(conn, user_id, filt)


_NO_ACCOUNT = -1
_EPOCH = dt.datetime.min.replace(tzinfo=dt.UTC)


def _group_delta(
    user_id: int,
    account_id: int,
    direction: Direction,
    *,
    is_source: bool,
    is_dest: bool,
    total: int,
) -> int:
    """Signed effect on ``account_id`` of one SUM group, via :func:`signed_legs` (ADR-0008)."""
    probe = Transaction(
        id=0,
        user_id=user_id,
        operation_date=dt.date.min,
        category_id=0,
        account_id=account_id if is_source else _NO_ACCOUNT,
        dest_account_id=account_id if is_dest else _NO_ACCOUNT,
        amount=total,
        description="",
        promoted_from_planned_id=None,
        promoted_from_recurring_rule_id=None,
        promoted_from_recurring_date=None,
        created_at=_EPOCH,
        updated_at=_EPOCH,
        deleted_at=None,
    )
    return sum(
        leg.amount_minor for leg in signed_legs(probe, direction) if leg.account_id == account_id
    )


def derive_balance(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    as_of_date: dt.date | None = None,
) -> int:
    """Return the derived balance in minor units of the account's own currency.

    - Ignores soft-deleted transactions.
    - ``as_of_date`` is inclusive. ``None`` means "latest".
    - Transit source and destination legs both apply.
    - Adjustment amounts pass through verbatim (signed).
    """
    account = accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    groups = transactions_repo.sum_legs_by_direction(
        conn, user_id, account_id, up_to_date=as_of_date
    )
    delta = sum(
        _group_delta(
            user_id,
            account_id,
            Direction(direction),
            is_source=is_source,
            is_dest=is_dest,
            total=total,
        )
        for direction, is_source, is_dest, total in groups
    )
    return account.opening_balance + delta


_Leg = tuple[dt.date, Direction, int]


def _legs_by_account(
    accounts: Sequence[Account],
    txns: Sequence[Transaction],
    directions: dict[int, Direction],
) -> dict[int, list[_Leg]]:
    """``(date, direction, signed amount)`` legs per account, for the given accounts only."""
    legs: dict[int, list[_Leg]] = {a.id: [] for a in accounts}
    for txn in txns:
        direction = directions[txn.category_id]
        for leg in signed_legs(txn, direction):
            if leg.account_id in legs:
                legs[leg.account_id].append((txn.operation_date, direction, leg.amount_minor))
    return legs


def _stats_from_legs(account: Account, legs: Sequence[_Leg]) -> AccountStats:
    inflows = [amt for _, d, amt in legs if d is Direction.INCOME]
    outflows = [abs(amt) for _, d, amt in legs if d is Direction.EXPENSE]
    balance_value = account.opening_balance + sum(amt for _, _, amt in legs)
    last_date = max((day for day, _, _ in legs), default=None)
    return AccountStats(
        account_id=account.id,
        balance=balance_value,
        base_balance=balance_value,
        txn_count=len(legs),
        last_txn_date=last_date.isoformat() if last_date is not None else None,
        avg_inflow_minor=mean_minor(sum(inflows), len(inflows)),
        avg_outflow_minor=mean_minor(sum(outflows), len(outflows)),
    )


def _stats_for(
    accounts: Sequence[Account],
    txns: Sequence[Transaction],
    directions: dict[int, Direction],
) -> dict[int, AccountStats]:
    """Per-account stats from ``txns`` (which must include every txn touching them)."""
    legs = _legs_by_account(accounts, txns, directions)
    return {a.id: _stats_from_legs(a, legs[a.id]) for a in accounts}


def account_stats(conn: sqlite3.Connection, user_id: int, account_id: int) -> AccountStats:
    """Current balance + descriptive stats. Pure; no caching.

    Averages consider only ``income`` / ``expense`` legs. Transit and
    adjustment legs contribute to ``txn_count`` and ``last_txn_date`` but
    not to the averages.
    """
    account = accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    return _stats_for(
        [account],
        _txns_affecting(conn, user_id, account_id),
        _directions_by_id(conn, user_id),
    )[account_id]


def account_stats_many(
    conn: sqlite3.Connection, user_id: int, accounts: Sequence[Account]
) -> dict[int, AccountStats]:
    """:func:`account_stats` for every account in ``accounts`` with two queries (T-Q234)."""
    return _stats_for(
        accounts,
        transactions_repo.list_filtered(conn, user_id, TransactionFilter()),
        _directions_by_id(conn, user_id),
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


def _group_effects(
    user_id: int,
    *,
    direction: str,
    account_id: int,
    dest_account_id: int | None,
    total: int,
) -> list[tuple[int, int]]:
    """``(account_id, signed delta)`` for every account one SUM group touches (ADR-0008)."""
    targets = {account_id} if dest_account_id is None else {account_id, dest_account_id}
    return [
        (
            target,
            _group_delta(
                user_id,
                target,
                Direction(direction),
                is_source=target == account_id,
                is_dest=target == dest_account_id,
                total=total,
            ),
        )
        for target in sorted(targets)
    ]


def derive_balances(
    conn: sqlite3.Connection,
    user_id: int,
    accounts: Sequence[Account],
    as_of_date: dt.date | None = None,
) -> dict[int, int]:
    """:func:`derive_balance` for every account in ``accounts`` with ONE query (T-Q234)."""
    deltas: dict[int, int] = {}
    for direction, account_id, dest_id, total in transactions_repo.sum_legs_by_account(
        conn, user_id, up_to_date=as_of_date
    ):
        for target, effect in _group_effects(
            user_id,
            direction=direction,
            account_id=account_id,
            dest_account_id=dest_id,
            total=total,
        ):
            deltas[target] = deltas.get(target, 0) + effect
    return {a.id: a.opening_balance + deltas.get(a.id, 0) for a in accounts}


def balance_series_many(
    conn: sqlite3.Connection,
    user_id: int,
    accounts: Sequence[Account],
    *,
    days: int = _DEFAULT_SERIES_DAYS,
    today: dt.date,
) -> dict[int, list[tuple[dt.date, int]]]:
    """Daily ``(date, balance)`` series per account, two queries total (T-Q234).

    Each series is oldest to newest, inclusive on both ends, ``days`` points long;
    the last point equals the balance as of ``today``. One query yields the balance
    before the window, one the per-day movements inside it; a running sum builds
    every series.
    """
    if days < 1:
        return {a.id: [] for a in accounts}
    start = today - dt.timedelta(days=days - 1)
    running = derive_balances(conn, user_id, accounts, as_of_date=start - dt.timedelta(days=1))
    moves: dict[dt.date, dict[int, int]] = {}
    for day, direction, account_id, dest_id, total in transactions_repo.sum_legs_by_day(
        conn, user_id, since=start, until=today
    ):
        day_moves = moves.setdefault(day, {})
        for target, effect in _group_effects(
            user_id,
            direction=direction,
            account_id=account_id,
            dest_account_id=dest_id,
            total=total,
        ):
            day_moves[target] = day_moves.get(target, 0) + effect
    out: dict[int, list[tuple[dt.date, int]]] = {a.id: [] for a in accounts}
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        todays = moves.get(day, {})
        for account_id, series in out.items():
            running[account_id] += todays.get(account_id, 0)
            series.append((day, running[account_id]))
    return out


def balance_series(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    *,
    days: int = _DEFAULT_SERIES_DAYS,
    today: dt.date,
) -> list[tuple[dt.date, int]]:
    """Daily ``(date, balance)`` series for one account; see :func:`balance_series_many`."""
    account = accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    return balance_series_many(conn, user_id, [account], days=days, today=today)[account_id]


__all__ = [
    "AccountNotFoundError",
    "SignedLeg",
    "account_stats",
    "account_stats_many",
    "balance_series",
    "balance_series_many",
    "derive_balance",
    "derive_balances",
    "signed_legs",
    "sparkline_points",
]
