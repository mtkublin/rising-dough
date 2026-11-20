"""T-Q06 repro: reconcile with a user-chosen income/expense category, and amount parsing edges.

Scratch DB only. Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-rec.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-rec.sqlite PYTHONPATH=. \
      uv run python docs/plans/quality-audit/repro/C/repro_reconcile_and_parse.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from decimal import Decimal

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

from budget_planner.config import Settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.domain.money import (  # noqa: E402
    currency_decimals,
    format_money,
    parse_amount_str,
    to_minor_units,
)
from budget_planner.services import balance, reconciliation  # noqa: E402

conn = get_connection(Settings())
TODAY = dt.date(2026, 11, 19)

print("== B1: reconcile(category=Groceries[expense]) when actual > derived ==")
acc = 1
derived = balance.derive_balance(conn, 1, acc)
actual = derived + 10_000  # bank says +100.00 more than we derived
txn = reconciliation.reconcile(conn, 1, acc, actual, TODAY, category_id=7)  # 7 = Groceries (expense)
after = balance.derive_balance(conn, 1, acc)
print(f"derived before={derived} actual target={actual} stored amount={txn.amount} after={after}")
print("MISMATCH: derive_balance != actual" if after != actual else "ok")

print("\n== B2: same with category=Salary[income] when actual < derived ==")
derived = balance.derive_balance(conn, 1, acc)
actual = derived - 5_000
txn = reconciliation.reconcile(conn, 1, acc, actual, TODAY, category_id=3)  # 3 = Salary (income)
after = balance.derive_balance(conn, 1, acc)
print(f"derived before={derived} actual target={actual} stored amount={txn.amount} after={after}")
print("MISMATCH: derive_balance != actual" if after != actual else "ok")

print("\n== P1: parse_amount_str / to_minor_units edge inputs (PLN) ==")
for raw in ("1e3", "1E-5", "1e30", "NaN", "Infinity", "-0", "0.00", "1_000", "١٢٣"):
    dec = parse_amount_str(raw, "PLN")
    if dec is None:
        print(f"{raw!r:12} -> rejected (None)")
        continue
    try:
        print(f"{raw!r:12} -> Decimal={dec!s:8} minor={to_minor_units(dec, 'PLN')}")
    except Exception as exc:  # noqa: BLE001
        print(f"{raw!r:12} -> parse accepted, to_minor_units raised {type(exc).__name__}")

print("\n== P2: reconcile route parses with bare Decimal(): NaN / Infinity ==")
for raw in ("NaN", "Infinity"):
    try:
        to_minor_units(Decimal(raw), "PLN")
    except Exception as exc:  # noqa: BLE001
        print(f"Decimal({raw!r}) -> to_minor_units raises {type(exc).__name__} (route catches only InvalidOperation around Decimal())")

print("\n== P3: currency exponent table ==")
for ccy in ("JPY", "KRW", "VND", "CLP", "ISK", "UGX", "KWD", "BHD", "JOD", "HUF"):
    print(f"{ccy}: decimals={currency_decimals(ccy)}  format_money(123456)={format_money(123456, ccy)}")

print("\n== P4: to_minor_units HALF_UP vs fx HALF_EVEN (x.5 case) ==")
print("to_minor_units(Decimal('0.125'),'PLN')... input is rejected at 3 digits by parse; FX path:")
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP  # noqa: E402

q = Decimal("2.5")
print("2.5 -> HALF_UP", q.quantize(Decimal(1), ROUND_HALF_UP), "HALF_EVEN", q.quantize(Decimal(1), ROUND_HALF_EVEN))
