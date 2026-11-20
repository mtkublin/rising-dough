"""A-09 / C-15 currency exponent table; A-08 / C-10 parsers."""

from decimal import Decimal

import _common  # noqa: F401  (sys.path)

from budget_planner.domain.money import currency_decimals, parse_amount_str, to_minor_units

for c in ("JPY", "KRW", "ISK", "CLP", "VND", "UGX", "BHD", "KWD", "JOD", "OMR", "TND", "HUF", "PLN"):
    print(c, currency_decimals(c))
print("ISK 1000 ->", to_minor_units(Decimal("1000"), "ISK"), "(true 0-decimal would be 1000)")
print("KWD 1.234 parse ->", parse_amount_str("1.234", "KWD"), "(3-decimal currency rejected)")
for raw in ("NaN", "Infinity", "1e400", "1e3", "1_000", "٣"):
    print(repr(raw), "canonical parse_amount_str ->", parse_amount_str(raw, "PLN"))
    try:
        d = Decimal(raw.replace(",", ".").strip())
        print("   bare Decimal(...) =", d, "-> to_minor_units:", end=" ")
        print(to_minor_units(d, "PLN"))
    except Exception as e:  # noqa: BLE001
        print("   bare path RAISES", type(e).__name__, str(e)[:60])
