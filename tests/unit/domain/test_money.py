from __future__ import annotations

from decimal import Decimal

import pytest

from budget_planner.domain.money import (
    currency_decimals,
    format_money,
    minor_to_major,
    parse_amount_str,
    to_minor_units,
)


def test_currency_decimals_defaults_to_two() -> None:
    assert currency_decimals("PLN") == 2
    assert currency_decimals("eur") == 2
    assert currency_decimals("ABC") == 2  # Unknown falls back to 2.
    assert currency_decimals("JPY") == 0
    assert currency_decimals("KRW") == 0


@pytest.mark.parametrize(
    ("major", "currency", "expected_minor"),
    [
        (Decimal("12.34"), "PLN", 1234),
        (Decimal("0.01"), "EUR", 1),
        (Decimal("-0.01"), "EUR", -1),
        (Decimal("1234"), "JPY", 1234),
        (Decimal("1234.5"), "JPY", 1235),  # rounds half-up
        (Decimal("0"), "USD", 0),
    ],
)
def test_to_minor_units(major: Decimal, currency: str, expected_minor: int) -> None:
    assert to_minor_units(major, currency) == expected_minor


def test_minor_to_major_round_trip() -> None:
    for amount in [-999999, -1, 0, 1, 500, 12345, 999999]:
        for ccy in ("PLN", "EUR", "USD", "JPY"):
            back = minor_to_major(amount, ccy)
            fwd = to_minor_units(back, ccy)
            assert fwd == amount, f"{ccy}:{amount} -> {back} -> {fwd}"


def test_format_money_positive_pln() -> None:
    assert format_money(123456, "PLN") == "1,234.56 PLN"


def test_format_money_negative() -> None:
    assert format_money(-5000, "USD") == "-50.00 USD"


def test_format_money_zero_decimals_currency() -> None:
    assert format_money(1234, "JPY") == "1,234 JPY"


def test_format_money_uppercases_currency() -> None:
    assert format_money(10, "eur") == "0.10 EUR"


# ---------------------------------------------------------------------------
# T-124 / ADR-0040 — parse_amount_str regression pin.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "currency", "expected"),
    [
        ("12.34", "PLN", Decimal("12.34")),
        ("12,34", "PLN", Decimal("12.34")),  # Polish/EU comma separator.
        ("  12,34  ", "PLN", Decimal("12.34")),  # Whitespace tolerated.
        ("0", "EUR", Decimal("0")),
        ("1234", "JPY", Decimal("1234")),  # Zero-decimal currency.
    ],
)
def test_parse_amount_str_accepts_both_separators(
    raw: str, currency: str, expected: Decimal
) -> None:
    assert parse_amount_str(raw, currency) == expected


@pytest.mark.parametrize(
    ("raw", "currency"),
    [
        ("12.345", "PLN"),  # Too many fractional digits for 2-decimal currency.
        ("12,345", "PLN"),  # Same via comma separator.
        ("1234.5", "JPY"),  # Any fraction illegal for zero-decimal currency.
        ("abc", "PLN"),  # Non-numeric.
        ("", "PLN"),  # Empty.
        ("   ", "PLN"),  # Whitespace only.
        ("NaN", "PLN"),  # Non-finite.
        ("Infinity", "PLN"),  # Non-finite.
    ],
)
def test_parse_amount_str_rejects_malformed(raw: str, currency: str) -> None:
    assert parse_amount_str(raw, currency) is None


def test_parse_amount_str_round_trip_to_minor_units_matches_dot_input() -> None:
    """Comma and dot inputs must land on the same minor-unit integer."""
    comma = parse_amount_str("12,34", "PLN")
    dot = parse_amount_str("12.34", "PLN")
    assert comma is not None
    assert dot is not None
    assert to_minor_units(comma, "PLN") == 1234
    assert to_minor_units(dot, "PLN") == 1234
