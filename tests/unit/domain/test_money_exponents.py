"""T-Q216 (ADR-0006 amendment 2026-11-21): complete exponent table and the one renderer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from budget_planner.domain.money import (
    CURRENCY_EXPONENTS,
    ISO_4217_CURRENCIES,
    bps_to_percent,
    currency_decimals,
    format_axis_number,
    format_bps_percent,
    format_major,
    format_money,
    major_float,
    minor_to_major,
    percent_of,
    percent_to_bps,
)
from budget_planner.web.templating import _money_num_filter


def test_every_offered_code_has_an_explicit_exponent() -> None:
    assert set(ISO_4217_CURRENCIES) <= set(CURRENCY_EXPONENTS)


@pytest.mark.parametrize(
    ("code", "exponent"),
    [
        ("ISK", 0),
        ("JPY", 0),
        ("CLP", 0),
        ("UGX", 0),
        ("KWD", 3),
        ("TND", 3),
        ("PLN", 2),
        ("HUF", 2),
    ],
)
def test_exponent_matches_iso_4217(code: str, exponent: int) -> None:
    assert currency_decimals(code) == exponent


def test_unknown_code_defaults_to_two_decimals() -> None:
    assert currency_decimals("ZZZ") == 2


def test_minor_to_major_is_exact_per_exponent() -> None:
    assert minor_to_major(123456, "PLN") == Decimal("1234.56")
    assert minor_to_major(123456, "JPY") == Decimal(123456)
    assert minor_to_major(1234567, "KWD") == Decimal("1234.567")


def test_money_num_filter_pln_equal_jpy_whole() -> None:
    assert _money_num_filter(123456, "PLN") == "1,234.56"
    assert _money_num_filter(123456, "JPY") == "123,456"
    assert format_money(123456, "JPY") == "123,456 JPY"


def test_format_major() -> None:
    assert format_major(1550, "PLN") == "15.50"
    assert format_major(1550, "JPY") == "1550"


def test_bps_helpers_round_trip() -> None:
    assert bps_to_percent(150) == Decimal("1.5")
    assert percent_to_bps(Decimal("12.345")) == 1234  # tie -> even (T-Q281; was 1235)
    assert format_bps_percent(1) == "0.01"


def test_percent_of_and_axis_and_float() -> None:
    assert percent_of(50, 200) == 25
    assert percent_of(5, 0) == 0
    assert format_axis_number(1200.0) == "1,200"
    assert format_axis_number(1.5) == "1.50"
    assert format_axis_number(-20000.0) == "\N{MINUS SIGN}20,000"
    assert format_axis_number(-1.5) == "\N{MINUS SIGN}1.50"
    assert format_axis_number(0.0) == "0"
    assert major_float(250, "PLN") == 2.5
    assert major_float(250, "JPY") == 250.0
