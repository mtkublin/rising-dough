# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-5: every user-amount parser gives the same verdict for the same text (Q-023).

Parsers compared: transactions._validate_amount (canonical: domain.money.parse_amount_str), planned._validate_amount,
accounts._parse_credit_limit, budget._parse_decimal + to_minor_units, today._afford_amount_minor. An uncaught exception
is an HTTP 500 at the router.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from budget_planner.domain.money import to_minor_units
from budget_planner.web.routers import accounts, budget, planned, today, transactions

INPUTS = [
    "12.34",
    "12,34",
    "12.345",
    " 12 ",
    "NaN",
    "Infinity",
    "1e400",
    "99999999999999999999",
    "1_000",
    "0x10",
    "12.5",
    "",
]


def _budget_parser(raw: str, ccy: str) -> Any:
    dec = budget._parse_decimal(raw)
    return None if dec is None else to_minor_units(dec, ccy)


def _today_parser(raw: str, ccy: str) -> Any:
    return today._afford_amount_minor(raw, ccy)


PARSERS: dict[str, Callable[[str, str], Any]] = {
    "transactions": transactions._validate_amount,
    "planned": planned._validate_amount,
    "accounts.credit_limit": accounts._parse_credit_limit,
    "budget": _budget_parser,
    "today.afford": _today_parser,
}


def _verdict(fn: Callable[[str, str], Any], raw: str, ccy: str) -> str:
    try:
        return repr(fn(raw, ccy))
    except Exception as exc:
        return f"CRASH {type(exc).__name__}"


def disagreements(ccy: str) -> list[str]:
    bad: list[str] = []
    for raw in INPUTS:
        normalised = set()
        for fn in PARSERS.values():
            v = _verdict(fn, raw, ccy)
            if v.startswith("CRASH"):
                normalised.add(v)
            elif "None" in v.split(",")[0] or ", '" in v:
                normalised.add("REJECT")
            else:
                normalised.add(v)
        if len(normalised) > 1:
            bad.append(raw)
    return bad


@pytest.mark.xfail(
    strict=True, reason="Q-023: seven hand-rolled amount parsers disagree and some crash (HTTP 500)"
)
@pytest.mark.parametrize("ccy", ["PLN", "JPY"])
def test_all_amount_parsers_agree(ccy: str) -> None:
    assert not disagreements(ccy)
