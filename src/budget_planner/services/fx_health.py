"""FX freshness decision for ``GET /health/fx`` (T-Q292, ADR-0146).

``evaluate`` is pure; ``check`` reads the cache once (never writes). Fail
closed: anything unknown is not healthy. The body carries currency codes and
dates only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from budget_planner.repositories import (
    accounts as accounts_repo,
    fx as fx_repo,
    users as users_repo,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrencyFreshness:
    """Newest cached rate of one used currency; ``None`` fields mean no rate at all."""

    code: str
    newest_date: date | None
    age_days: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FxHealth:
    """Verdict for ``GET /health/fx``. ``ok`` maps to HTTP 200."""

    ok: bool
    status: str
    currencies: tuple[CurrencyFreshness, ...]
    max_age_days: int
    checked_at: str

    def body(self) -> dict[str, object]:
        return {
            "status": self.status,
            "currencies": [
                {
                    "code": c.code,
                    "newest_date": c.newest_date.isoformat() if c.newest_date else None,
                    "age_days": c.age_days,
                }
                for c in self.currencies
            ],
            "max_age_days": self.max_age_days,
            "checked_at": self.checked_at,
        }


def _verdict(
    *,
    ok: bool,
    status: str,
    currencies: tuple[CurrencyFreshness, ...],
    max_age_days: int,
    now: datetime,
) -> FxHealth:
    return FxHealth(
        ok=ok,
        status=status,
        currencies=currencies,
        max_age_days=max_age_days,
        checked_at=now.isoformat(),
    )


def disabled(*, required: bool = False, max_age_days: int, now: datetime) -> FxHealth:
    """Refresh not active. Healthy outside production; ``ok=False`` in production (T-Q307)."""
    return _verdict(
        ok=not required, status="disabled", currencies=(), max_age_days=max_age_days, now=now
    )


def unavailable(*, max_age_days: int, now: datetime) -> FxHealth:
    """The check itself failed: 503, never healthy."""
    return _verdict(ok=False, status="error", currencies=(), max_age_days=max_age_days, now=now)


def crashed(*, max_age_days: int, now: datetime) -> FxHealth:
    """The refresh task died of an unexpected error (T-Q314): 503 until the operator restarts."""
    return _verdict(
        ok=False, status="refresh_crashed", currencies=(), max_age_days=max_age_days, now=now
    )


def evaluate(
    used: Iterable[tuple[str, date | None]],
    *,
    today: date,
    max_age_days: int,
    now: datetime,
) -> FxHealth:
    """Judge ``(currency, newest rate date | None)`` pairs against ``today``."""
    rows = tuple(
        CurrencyFreshness(
            code=code,
            newest_date=newest,
            age_days=None if newest is None else max((today - newest).days, 0),
        )
        for code, newest in sorted(used)
    )
    if not rows:
        return _verdict(ok=True, status="ok", currencies=(), max_age_days=max_age_days, now=now)
    if any(r.age_days is None for r in rows):
        status = "never"
    elif any(r.age_days is not None and r.age_days > max_age_days for r in rows):
        status = "stale"
    else:
        status = "ok"
    return _verdict(
        ok=status == "ok", status=status, currencies=rows, max_age_days=max_age_days, now=now
    )


def _newest_by_used_currency(
    conn: sqlite3.Connection, base_currency: str
) -> list[tuple[str, date | None]]:
    """Foreign currencies of every live user's live accounts, each user scoped separately."""
    codes = {
        a.currency
        for user in users_repo.list_live(conn)
        for a in accounts_repo.list_all(conn, user.id)
        if a.currency != base_currency
    }
    newest_by_code: dict[str, date] = {}
    for cached in fx_repo.list_rates_to(conn, base_currency):
        newest_by_code[cached.from_ccy] = max(
            cached.date, newest_by_code.get(cached.from_ccy, cached.date)
        )
    return [(code, newest_by_code.get(code)) for code in sorted(codes)]


def check(
    conn: sqlite3.Connection,
    *,
    base_currency: str,
    refresh_active: bool,
    refresh_required: bool = False,
    today: date,
    max_age_days: int,
    now: datetime,
) -> FxHealth:
    """Read the cache (all users' live accounts, ADR-0146 section 5) and decide.

    ``refresh_required`` (production) turns an inactive refresh into a failure (T-Q307).
    """
    if not refresh_active:
        return disabled(required=refresh_required, max_age_days=max_age_days, now=now)
    used = _newest_by_used_currency(conn, base_currency)
    return evaluate(used, today=today, max_age_days=max_age_days, now=now)
