# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-5: every user-amount entry point gives the same verdict for the same text (Q-023, T-Q233).

All parsers route through ``domain.money.parse_amount_minor``; this pins the verdict (exact minor units or
rejection) across the router wrappers and that no input raises (an uncaught exception is an HTTP 500).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from budget_planner.web.params import credit_limit_amount, positive_amount

REJECT = "REJECT"

EXPECTED_PLN: dict[str, int | str] = {
    "12.34": 1234,
    "12,34": 1234,
    "12.345": REJECT,
    " 12 ": 1200,
    "NaN": REJECT,
    "Infinity": REJECT,
    "1e400": REJECT,
    "1e3": REJECT,
    "99999999999999999999": REJECT,
    "1_000": REJECT,
    "0x10": REJECT,
    "١٢": REJECT,
    "12.5": 1250,
}
EXPECTED_JPY: dict[str, int | str] = {
    "12.34": REJECT,
    "12,34": REJECT,
    "12.345": REJECT,
    " 12 ": 12,
    "NaN": REJECT,
    "Infinity": REJECT,
    "1e400": REJECT,
    "99999999999999999999": REJECT,
    "1_000": REJECT,
    "0x10": REJECT,
    "12.5": REJECT,
}


def _transactions(raw: str, ccy: str) -> int | str:
    minor, err = positive_amount(raw, ccy)
    return REJECT if err is not None or minor is None else minor


def _credit_limit(raw: str, ccy: str) -> int | str:
    minor, err = credit_limit_amount(raw, ccy)
    return REJECT if err is not None or minor is None else minor


PARSERS: dict[str, Callable[[str, str], int | str]] = {
    "transactions/planned/recurring/today.afford": _transactions,
    "accounts.credit_limit": _credit_limit,
}


@pytest.mark.parametrize("name", PARSERS)
@pytest.mark.parametrize(
    ("ccy", "expected"), [("PLN", EXPECTED_PLN), ("JPY", EXPECTED_JPY)], ids=["PLN", "JPY"]
)
def test_all_amount_parsers_agree(name: str, ccy: str, expected: dict[str, int | str]) -> None:
    parser = PARSERS[name]
    assert {raw: parser(raw, ccy) for raw in expected} == expected
