"""Data assembly shared by the Today surface (T-D50 / ADR-0077).

Moved from the retired home router: account rows, pace tag, upcoming window
and the upcoming-row view model. No business logic — services only.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from fastapi import Request

from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import (
    balance as balance_service,
    fx as fx_service,
    upcoming as upcoming_service,
)

PaceKind = Literal["on_track", "pacing_high", "over_budget"]

_PACE_LABELS: Final[dict[str, str]] = {
    "on_track": "on track",
    "pacing_high": "pacing high",
    "over_budget": "over budget",
}

_WINDOWS: Final[dict[str, int | None]] = {"7": 7, "30": 30, "all": None}
_DEFAULT_WINDOW: Final[str] = "30"


@dataclass(frozen=True, slots=True)
class AccountRow:
    """Per-account row for Panel A."""

    id: int
    name: str
    type: str | None
    currency: str
    balance_minor: int
    balance_base_minor: int


@dataclass(frozen=True, slots=True)
class CurrencyTotal:
    """Per-currency total for Panel A sub-header."""

    currency: str
    total_minor: int


@dataclass(frozen=True, slots=True)
class PaceTag:
    """Pace signal for Panel B — label + semantic kind."""

    kind: PaceKind
    label: str


@dataclass(frozen=True, slots=True)
class UpcomingRow:
    """Normalised row for Panel C (T-121 — planned + recurring).

    ``planned_id`` / ``rule_id`` are mutually exclusive (one is always
    ``None``), set according to ``kind``. ``override_present`` is only
    meaningful for recurring rows (planned rows always set it to False).
    """

    operation_date: date
    description: str
    amount_minor: int
    is_overdue: bool
    kind: str  # "planned" | "recurring" — drives the row's data-kind attribute.
    planned_id: int | None
    rule_id: int | None
    override_present: bool
    is_formula: bool
    category_id: int
    account_id: int
    dest_account_id: int | None


def collect_account_rows(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_service.FxConverter,
) -> tuple[tuple[AccountRow, ...], tuple[CurrencyTotal, ...], int]:
    """Return (per-account rows, per-currency totals, fortune in base)."""
    accs = accounts_repo.list_all(conn, user_id)
    per_ccy: dict[str, int] = {}
    native: list[tuple[int, str, str | None, str, int]] = []
    for a in accs:
        bal = balance_service.derive_balance(conn, user_id, a.id)
        per_ccy[a.currency] = per_ccy.get(a.currency, 0) + bal
        native.append((a.id, a.name, a.type, a.currency, bal))

    rows = tuple(
        AccountRow(
            id=aid,
            name=name,
            type=atype,
            currency=ccy,
            balance_minor=bal,
            balance_base_minor=fx.to_base(bal, ccy),
        )
        for (aid, name, atype, ccy, bal) in native
    )
    totals = tuple(
        CurrencyTotal(currency=ccy, total_minor=total) for ccy, total in sorted(per_ccy.items())
    )
    fortune_base = sum(r.balance_base_minor for r in rows)
    return rows, totals, fortune_base


def pace_tag(spent: int, budgeted: int, today: date, year: int, month: int) -> PaceTag:
    """Compute pace signal from totals + elapsed fraction of the month."""
    if budgeted <= 0:
        return PaceTag(kind="on_track", label=_PACE_LABELS["on_track"])
    if spent > budgeted:
        return PaceTag(kind="over_budget", label=_PACE_LABELS["over_budget"])
    days_in_month = calendar.monthrange(year, month)[1]
    elapsed = today.day if (today.year == year and today.month == month) else days_in_month
    expected = budgeted * elapsed // days_in_month
    if spent > expected:
        return PaceTag(kind="pacing_high", label=_PACE_LABELS["pacing_high"])
    return PaceTag(kind="on_track", label=_PACE_LABELS["on_track"])


def window_from(request: Request) -> tuple[str, int | None]:
    """Parse ``?window=`` → (label, days). Falls back to the default."""
    raw = request.query_params.get("window", _DEFAULT_WINDOW)
    if raw not in _WINDOWS:
        raw = _DEFAULT_WINDOW
    return raw, _WINDOWS[raw]


def list_upcoming(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    window_days: int | None,
) -> tuple[UpcomingRow, ...]:
    """Return the Panel C row set — planned one-offs + recurring next_due.

    T-119: delegates to ``services.upcoming.list_upcoming`` which composes
    persisted planned rows (``promoted=False``) with active recurring
    rules (ADR-0038) and applies ``next_due`` overrides. ``window_days``
    forwards unchanged.
    """
    items = upcoming_service.list_upcoming(conn, user_id, today=today, window_days=window_days)
    return tuple(
        UpcomingRow(
            operation_date=item.effective_date,
            description=item.description,
            amount_minor=item.amount_minor,
            is_overdue=item.is_overdue,
            kind=item.kind,
            planned_id=item.planned_id,
            rule_id=item.rule_id,
            override_present=item.override_present,
            is_formula=item.is_formula,
            category_id=item.category_id,
            account_id=item.account_id,
            dest_account_id=item.dest_account_id,
        )
        for item in items
    )
