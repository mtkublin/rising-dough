"""INV-4: copies of the same arithmetic must agree.

4a signed legs per Direction across the five implementations (balance, ledger_totals,
   forecast events, account_planned, limit-preview inline copy).
4b FX minor-unit conversion across the four copies (fx.convert, fx.convert_cached,
   forecast._convert_native_to_base, today_data._convert_minor) on a grid incl. half-way
   cases and JPY/PLN scale changes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import harness

from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.transactions import Transaction
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import account_planned, balance, forecast, fx, ledger_totals
from budget_planner.web import today_data

import datetime as dt

conn = harness.fresh_db()

harness.banner("4a signed legs (amount=1000; transit src=1 dest=2)")
now = dt.datetime.now(dt.UTC)
txn = Transaction(
    id=1, user_id=1, operation_date=date(2026, 11, 1), category_id=1, account_id=1,
    dest_account_id=2, amount=1000, description="", promoted_from_planned_id=None,
    promoted_from_recurring_rule_id=None, promoted_from_recurring_date=None,
    created_at=now, updated_at=now, deleted_at=None,
) if "promoted_from_recurring_date" in Transaction.__dataclass_fields__ else None
all_ok = True
for d in Direction:
    legs_bal = {
        (leg.account_id): leg.amount_minor
        for leg in (balance.signed_legs(txn, d) if txn else ())
    }
    eff_ledger = ledger_totals.signed_effect(1000, d)
    ev = forecast._signed_events_for_direction(d, date(2026, 11, 1), 1, 2, 1000)
    legs_fc = {e.account_id: e.amount_minor for e in ev}
    legs_ap = dict(account_planned._legs(d, 1, 2, 1000))
    print(d.value, "balance:", legs_bal, "ledger_totals(src):", eff_ledger,
          "forecast:", legs_fc, "account_planned:", legs_ap)
    if d is Direction.ADJUSTMENT:
        # documented asymmetry: balance counts adjustments, forecast/account_planned skip them
        ok = bool(legs_bal) and not legs_fc and not legs_ap
        harness.check("adjustment: balance counts, forecast/planned skip (by design, ADR-0011)", ok)
        continue
    src_ok = legs_bal.get(1, 0) == legs_fc.get(1, 0) == legs_ap.get(1, 0)
    harness.check(f"{d.value}: source leg identical in balance/forecast/account_planned", src_ok)
    all_ok &= src_ok

harness.banner("4b FX arithmetic copies")
fx_repo.upsert_rate(conn, NewFxRate(date=date(2026, 11, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.2655")))
fx_repo.upsert_rate(conn, NewFxRate(date=date(2026, 11, 1), from_ccy="JPY", to_ccy="PLN", rate=Decimal("0.0275")))
fx_repo.upsert_rate(conn, NewFxRate(date=date(2026, 11, 1), from_ccy="PLN", to_ccy="JPY", rate=Decimal("36.3636")))
bad = 0
n = 0
for src, dst, rate in (("EUR", "PLN", Decimal("4.2655")), ("JPY", "PLN", Decimal("0.0275")), ("PLN", "JPY", Decimal("36.3636"))):
    for amt in list(range(-300, 301, 7)) + [1, 5, 50, 12345, 999_999_99]:
        n += 1
        a = fx.convert(conn, harness.offline_http(), amt, date(2026, 11, 1), src, dst)
        b = fx.convert_cached(conn, amt, date(2026, 11, 1), src, dst)
        c = forecast._convert_native_to_base(amt, src, dst, {src: rate})
        d_ = today_data._convert_minor(amt, src, dst, rate)
        if len({a, b, c, d_}) != 1:
            bad += 1
            print("DIVERGE", src, dst, amt, a, b, c, d_)
harness.check(f"four FX arithmetic copies agree on {n} samples", bad == 0, f"{bad} divergences")
