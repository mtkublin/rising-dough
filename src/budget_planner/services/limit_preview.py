"""Credit-limit projection for the transaction form (ADR-0024, T-Q265).

Soft-failing by design: any missing or unparseable input yields ``None`` so the
form fragment stays blank while the user keeps editing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from budget_planner.domain.money import parse_amount_str, to_minor_units
from budget_planner.domain.transactions import signed_legs
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    categories as categories_service,
    transactions as transactions_service,
)


@dataclass(frozen=True, slots=True)
class LimitPreview:
    """Projected utilisation snapshot for the transaction form (ADR-0024)."""

    projected_balance: int
    available_before: int
    available_after: int
    used_after: int
    limit: int
    over_by: int
    currency: str
    account_name: str


def compute_limit_preview(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    account_id: int,
    category_id: int | None,
    amount_raw: str,
    exclude_txn_id: int | None = None,
) -> LimitPreview | None:
    """Project post-transaction utilization for a liability account.

    ``category_id=None`` (no category picked yet) previews only a zero amount: it moves nothing, so
    the line shows before = after (the handoff's 422 dialog keeps its line).

    ``exclude_txn_id`` (edit mode, ADR-0134 §2): the caller's transaction being edited is left out
    of the "before" balance so its current amount is not counted twice. A foreign or unknown id is
    ignored.
    """
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None or not acc.is_liability or acc.credit_limit_minor is None:
        return None
    delta = _delta(
        conn,
        user_id,
        currency=acc.currency,
        account_id=account_id,
        category_id=category_id,
        amount_raw=amount_raw,
    )
    if delta is None:
        return None
    current = balance_service.derive_balance(conn, user_id, account_id) - _edited_effect(
        conn, user_id, account_id, exclude_txn_id
    )
    projected = current + delta
    limit = acc.credit_limit_minor
    used_before = max(-current, 0)
    used_after = max(-projected, 0)
    return LimitPreview(
        projected_balance=projected,
        available_before=max(limit - used_before, 0),
        available_after=max(limit - used_after, 0),
        used_after=used_after,
        limit=limit,
        over_by=max(used_after - limit, 0),
        currency=acc.currency,
        account_name=acc.name,
    )


def _delta(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    currency: str,
    account_id: int,
    category_id: int | None,
    amount_raw: str,
) -> int | None:
    """Signed effect of the typed amount on the account; ``None`` when there is no preview."""
    dec = parse_amount_str(amount_raw, currency)
    if dec is None or dec < 0:
        return None
    if category_id is None:
        return 0 if dec == 0 else None
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return None
    # Only the source leg matters for this account; a transit's destination is irrelevant here.
    amount_minor = to_minor_units(dec, currency)
    return signed_legs(cat.direction, amount_minor, account_id, account_id)[0].amount_minor


def _edited_effect(
    conn: sqlite3.Connection, user_id: int, account_id: int, txn_id: int | None
) -> int:
    """Signed effect of the caller's own transaction ``txn_id`` on ``account_id`` (0 if none)."""
    if txn_id is None:
        return 0
    txn = transactions_service.find_by_id(conn, user_id, txn_id)
    if txn is None:
        return 0
    cat = categories_service.find_by_id(conn, user_id, txn.category_id, include_deleted=True)
    if cat is None:
        return 0
    legs = signed_legs(cat.direction, txn.amount, txn.account_id, txn.dest_account_id)
    return sum(leg.amount_minor for leg in legs if leg.account_id == account_id)
