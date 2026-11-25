from __future__ import annotations

from decimal import Decimal

import pytest

from budget_planner.domain.money import (
    ascii_minus,
    currency_decimals,
    format_figure,
    format_major,
    format_money,
    format_whole,
    minor_to_major,
    parse_amount_minor,
    parse_amount_str,
    sign_glyph,
    to_minor_units,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\N{MINUS SIGN}12.50", "-12.50"),
        ("-3", "-3"),
        ("+", "+"),
        ("", ""),
        ("1\N{MINUS SIGN}2", "1-2"),
    ],
)
def test_ascii_minus(text: str, expected: str) -> None:
    assert ascii_minus(text) == expected


def test_sign_glyph() -> None:
    assert sign_glyph(True) == "\N{MINUS SIGN}"
    assert sign_glyph(False) == "+"


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
        (Decimal("1234.5"), "JPY", 1234),  # tie -> even neighbour (T-Q281; was half-up 1235)
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


_M = chr(0x2212)


@pytest.mark.parametrize(
    ("minor", "currency", "kwargs", "expected"),
    [
        (-123456, "PLN", {}, _M + "1,234.56"),
        (1200, "PLN", {"plus": True}, "+12.00"),
        (1200, "PLN", {}, "12.00"),
        (0, "PLN", {"plus": True}, "0.00"),
        (-70000, "JPY", {}, _M + "70,000"),
        (-123456, "PLN", {"with_currency": True}, _M + "1,234.56 PLN"),
        (1200, "PLN", {"plus": True, "with_currency": True}, "+12.00 PLN"),
    ],
)
def test_format_figure(minor: int, currency: str, kwargs: dict[str, bool], expected: str) -> None:
    assert format_figure(minor, currency, **kwargs) == expected


def test_format_money_positive_pln() -> None:
    assert format_money(123456, "PLN") == "1,234.56 PLN"


def test_format_money_negative() -> None:
    assert format_money(-5000, "USD") == "-50.00 USD"


def test_format_money_zero_decimals_currency() -> None:
    assert format_money(1234, "JPY") == "1,234 JPY"


@pytest.mark.parametrize(
    ("currency", "expected"), [("PLN", "0.00 PLN"), ("JPY", "0 JPY")], ids=["PLN", "JPY"]
)
def test_format_money_zero(currency: str, expected: str) -> None:
    assert format_money(0, currency) == expected


def test_format_money_minus_one_jpy_keeps_sign() -> None:
    assert format_money(-1, "JPY") == "-1 JPY"


@pytest.mark.parametrize("amount_minor", [-49, -1, 0, 49])
def test_format_whole_rounds_to_zero_without_sign(amount_minor: int) -> None:
    assert format_whole(amount_minor, "PLN") == "0"
    assert format_whole(amount_minor, "PLN", grouped=False) == "0"


def test_format_whole_keeps_sign_when_nonzero() -> None:
    assert format_whole(-150, "PLN") == "-2"  # 1.5 -> 2
    assert format_whole(-250, "PLN") == "-2"  # 2.5 -> even 2 (T-Q281; was -3)
    assert format_whole(-51, "PLN") == "-1"


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2,239.80", Decimal("2239.80")),  # grouped, as an edit dialog prefills it
        ("1,234,567.50", Decimal("1234567.50")),
        ("-1,000.00", Decimal("-1000.00")),
    ],
)
def test_parse_amount_str_accepts_grouped_thousands_before_a_dot(
    raw: str, expected: Decimal
) -> None:
    assert parse_amount_str(raw, "PLN") == expected


@pytest.mark.parametrize("raw", ["2,23.80", "12,3456.00", ",239.80", "2,239,.80", "1.234,50"])
def test_parse_amount_str_rejects_misplaced_grouping(raw: str) -> None:
    assert parse_amount_str(raw, "PLN") is None


@pytest.mark.parametrize(
    ("raw", "currency", "minor"),
    [
        ("2,50", "PLN", 250),  # a lone comma stays the decimal separator
        ("12,34", "PLN", 1234),
        ("2,239.80", "PLN", 223_980),  # grouping only when a dot follows
        ("1,234.00", "PLN", 123_400),
        ("1,234", "JPY", None),  # no dot: the decimal reading, not allowed for a yen amount
        ("1,234", "PLN", None),  # decimal reading has three decimals: rejected, never 1234.00
        ("1 234,56", "PLN", None),  # a space is not a separator
        ("1.234,56", "PLN", None),  # European grouping is not read
    ],
)
def test_parse_amount_minor_keeps_the_meaning_of_ambiguous_commas(
    raw: str, currency: str, minor: int | None
) -> None:
    assert parse_amount_minor(raw, currency) == minor


def test_format_major_grouped_round_trips_and_leaves_zero_decimals_bare() -> None:
    assert format_major(223_980, "PLN") == "2239.80"
    assert format_major(223_980, "PLN", grouped=True) == "2,239.80"
    assert format_major(99_999, "PLN", grouped=True) == "999.99"
    assert format_major(123_456, "JPY", grouped=True) == "123456"  # "1,234" would read as 1.234
    assert parse_amount_str(format_major(123_456_789, "PLN", grouped=True), "PLN") == Decimal(
        "1234567.89"
    )


def test_parse_amount_str_round_trip_to_minor_units_matches_dot_input() -> None:
    """Comma and dot inputs must land on the same minor-unit integer."""
    comma = parse_amount_str("12,34", "PLN")
    dot = parse_amount_str("12.34", "PLN")
    assert comma is not None
    assert dot is not None
    assert to_minor_units(comma, "PLN") == 1234
    assert to_minor_units(dot, "PLN") == 1234
