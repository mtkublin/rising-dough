"""INV-5: every user-amount parser must give the same verdict for the same text (PLN, JPY).

Parsers compared: transactions._validate_amount (canonical: domain.money.parse_amount_str),
planned._validate_amount, accounts._parse_credit_limit, budget._parse_decimal + to_minor_units,
today._parse_amount_arg. An uncaught exception == HTTP 500 at the router.
"""

from __future__ import annotations

import harness

harness.fresh_db()

from budget_planner.domain.money import to_minor_units  # noqa: E402
from budget_planner.web.routers import accounts, budget, planned, today, transactions  # noqa: E402

INPUTS = ["12.34", "12,34", "12.345", " 12 ", "NaN", "Infinity", "1e400", "99999999999999999999", "1_000", "0x10", "12.5", ""]


def verdict(fn, raw: str, ccy: str) -> str:
    try:
        return repr(fn(raw, ccy))
    except Exception as exc:  # noqa: BLE001 - we want to record every crash
        return f"CRASH {type(exc).__name__}"


def budget_parser(raw: str, ccy: str):
    dec = budget._parse_decimal(raw)
    return None if dec is None else to_minor_units(dec, ccy)


def today_parser(raw: str, _ccy: str):
    return today._parse_amount_arg(raw)


PARSERS = {
    "transactions": transactions._validate_amount,
    "planned": planned._validate_amount,
    "accounts.credit_limit": accounts._parse_credit_limit,
    "budget": budget_parser,
    "today.afford": today_parser,
}

for ccy in ("PLN", "JPY"):
    harness.banner(f"currency {ccy}")
    disagreements = 0
    for raw in INPUTS:
        row = {name: verdict(fn, raw, ccy) for name, fn in PARSERS.items()}
        print(f"{raw!r:26}", row)
        # compare only the (minor, error) -> minor part: treat error tuples as 'REJECT'
        norm = set()
        for v in row.values():
            if v.startswith("CRASH"):
                norm.add(v)
            elif "None" in v.split(",")[0] or ", '" in v:
                norm.add("REJECT")
            else:
                norm.add(v)
        if len(norm) > 1:
            disagreements += 1
    harness.check("all parsers agree on every input", disagreements == 0, f"{disagreements} inputs disagree")
