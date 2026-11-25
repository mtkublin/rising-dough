"""Money helpers.

Amounts are stored as signed integer minor units of the account currency
(ADR-0008 / ADR-0006). All conversion between major-unit ``Decimal`` and
integer minor units routes through this module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import Final

# ISO 4217 active currency codes (ADR-0030). Alphabetical order so the combobox
# surfaces predictable results. Not exhaustive — the subset below covers every
# currency the app is expected to see in v1 while giving the user a familiar
# dropdown. Validation at the service boundary still accepts any three-letter
# ISO code so adding a less-common currency does not require a code change.
ISO_4217_CURRENCIES: Final[tuple[str, ...]] = (
    "AED",
    "AFN",
    "ALL",
    "AMD",
    "ANG",
    "AOA",
    "ARS",
    "AUD",
    "AWG",
    "AZN",
    "BAM",
    "BBD",
    "BDT",
    "BGN",
    "BHD",
    "BIF",
    "BMD",
    "BND",
    "BOB",
    "BRL",
    "BSD",
    "BTN",
    "BWP",
    "BYN",
    "BZD",
    "CAD",
    "CDF",
    "CHF",
    "CLP",
    "CNY",
    "COP",
    "CRC",
    "CUP",
    "CVE",
    "CZK",
    "DJF",
    "DKK",
    "DOP",
    "DZD",
    "EGP",
    "ERN",
    "ETB",
    "EUR",
    "FJD",
    "FKP",
    "GBP",
    "GEL",
    "GHS",
    "GIP",
    "GMD",
    "GNF",
    "GTQ",
    "GYD",
    "HKD",
    "HNL",
    "HTG",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "IQD",
    "IRR",
    "ISK",
    "JMD",
    "JOD",
    "JPY",
    "KES",
    "KGS",
    "KHR",
    "KMF",
    "KPW",
    "KRW",
    "KWD",
    "KYD",
    "KZT",
    "LAK",
    "LBP",
    "LKR",
    "LRD",
    "LSL",
    "LYD",
    "MAD",
    "MDL",
    "MGA",
    "MKD",
    "MMK",
    "MNT",
    "MOP",
    "MRU",
    "MUR",
    "MVR",
    "MWK",
    "MXN",
    "MYR",
    "MZN",
    "NAD",
    "NGN",
    "NIO",
    "NOK",
    "NPR",
    "NZD",
    "OMR",
    "PAB",
    "PEN",
    "PGK",
    "PHP",
    "PKR",
    "PLN",
    "PYG",
    "QAR",
    "RON",
    "RSD",
    "RUB",
    "RWF",
    "SAR",
    "SBD",
    "SCR",
    "SDG",
    "SEK",
    "SGD",
    "SHP",
    "SLE",
    "SOS",
    "SRD",
    "SSP",
    "STN",
    "SVC",
    "SYP",
    "SZL",
    "THB",
    "TJS",
    "TMT",
    "TND",
    "TOP",
    "TRY",
    "TTD",
    "TWD",
    "TZS",
    "UAH",
    "UGX",
    "USD",
    "UYU",
    "UZS",
    "VES",
    "VND",
    "VUV",
    "WST",
    "XAF",
    "XCD",
    "XDR",
    "XOF",
    "XPF",
    "YER",
    "ZAR",
    "ZMW",
    "ZWL",
)


# ISO 4217 minor-unit exponents (ADR-0006 amendment 2026-11-21). Every offered
# code has an explicit entry; the groups below are the non-default exponents.
_ZERO_DECIMAL: Final[frozenset[str]] = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
_THREE_DECIMAL: Final[frozenset[str]] = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
CURRENCY_EXPONENTS: Final[Mapping[str, int]] = MappingProxyType(
    {
        code: 0 if code in _ZERO_DECIMAL else 3 if code in _THREE_DECIMAL else 2
        for code in ISO_4217_CURRENCIES
    }
)
_DEFAULT_EXPONENT: Final = 2

# Rounding policy (ADR-0006 amendment 2026-11-22, T-Q281): one mode, half to even, at
# every call site; the two helpers below are the only quantize points.
_ONE: Final = Decimal(1)


def round_scaled(value: Decimal) -> int:
    """Round a ``Decimal`` to the nearest integer, ties to even (the one quantize point)."""
    return int(value.quantize(_ONE, rounding=ROUND_HALF_EVEN))


def round_div(numerator: int, denominator: int) -> int:
    """Integer ratio ``numerator / denominator`` rounded to the nearest integer, ties to even."""
    return round_scaled(Decimal(numerator) / Decimal(denominator))


_BPS_PER_PERCENT: Final = Decimal(100)


def currency_decimals(currency: str) -> int:
    """Return the ISO 4217 minor-unit exponent for ``currency`` (2 for unknown codes)."""
    return CURRENCY_EXPONENTS.get(currency.upper(), _DEFAULT_EXPONENT)


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal major-unit amount to signed integer minor units.

    Rounds ties to even (T-Q281). Does not clamp the magnitude.
    """
    decimals = currency_decimals(currency)
    quant = Decimal(10) ** -decimals
    quantised = amount.quantize(quant, rounding=ROUND_HALF_EVEN)
    return int(quantised * (Decimal(10) ** decimals))


MAX_MINOR: Final = 10**15
"""Largest accepted absolute amount in minor units (T-Q233, Q-023); far below SQLite's int64."""

_AMOUNT_RE: Final = re.compile(r"[+-]?\d+(?:\.(\d+))?", re.ASCII)
_GROUPED_RE: Final = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+\.\d+", re.ASCII)


def parse_amount_str(raw: str, currency: str) -> Decimal | None:
    """Parse a user-entered amount string into a Decimal (T-124 / ADR-0040, T-Q233).

    The one amount parser (Q-023). Returns ``None`` (the router surfaces a 422) for:

    - anything but ASCII digits with an optional sign and one ``.`` or ``,`` separator, or
      thousands grouped by commas before a ``.`` (``2,239.80``); no exponents,
      ``NaN``/``Infinity``, underscores, non-ASCII digits, hex;
    - more fractional digits than the currency supports (``12.345`` for PLN);
    - an absolute value above ``MAX_MINOR`` minor units.
    """
    text = raw.strip()
    if _GROUPED_RE.fullmatch(text):  # "2,239.80": commas group thousands when a "." follows
        text = text.replace(",", "")
    normalised = text.replace(",", ".")
    match = _AMOUNT_RE.fullmatch(normalised)
    if match is None:
        return None
    decimals = currency_decimals(currency)
    if len(match.group(1) or "") > decimals:
        return None
    dec = Decimal(normalised)
    if abs(dec) * (Decimal(10) ** decimals) > MAX_MINOR:
        return None
    return dec


def parse_amount_minor(raw: str, currency: str) -> int | None:
    """Parse ``raw`` straight to signed minor units (``None`` when invalid or out of range)."""
    dec = parse_amount_str(raw, currency)
    return None if dec is None else to_minor_units(dec, currency)


def minor_to_major(amount_minor: int, currency: str) -> Decimal:
    """Convert signed minor units back to a ``Decimal`` major-unit amount."""
    decimals = currency_decimals(currency)
    return Decimal(amount_minor) / (Decimal(10) ** decimals)


def format_money(amount_minor: int, currency: str) -> str:
    """Render as e.g. ``'1,234.56 PLN'`` or ``'1,234 JPY'``.

    Preserves sign for negative values. Zero renders without a sign.
    """
    decimals = currency_decimals(currency)
    value = minor_to_major(amount_minor, currency)
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole, _, frac = f"{value:,.{decimals}f}".partition(".")
    return f"{sign}{whole}{('.' + frac) if frac else ''} {currency.upper()}"


_MINUS: Final = "\N{MINUS SIGN}"


def ascii_minus(text: str) -> str:
    """Typed text with the display minus (U+2212) turned back into ``-`` for parsing."""
    return text.replace(_MINUS, "-")


def sign_glyph(negative: bool) -> str:
    """Display sign of an amount: U+2212 when ``negative``, ``+`` otherwise."""
    return _MINUS if negative else "+"


def format_figure(
    amount_minor: int, currency: str, *, plus: bool = False, with_currency: bool = False
) -> str:
    """Signed display figure: U+2212 for negatives, ``+`` for positives when ``plus``.

    Magnitude comes from ``format_money`` (grouping, exponent); zero carries no sign.
    The currency suffix is added only with ``with_currency``.
    """
    text = format_money(abs(amount_minor), currency)
    if not with_currency:
        text = text.rsplit(" ", 1)[0]
    if amount_minor < 0:
        return _MINUS + text
    return "+" + text if plus and amount_minor > 0 else text


def bps_to_percent(bps: int) -> Decimal:
    """Basis points as a percent ``Decimal`` (150 -> 1.5); not a currency amount."""
    return Decimal(bps) / _BPS_PER_PERCENT


_INT_LABEL_EPSILON: Final = 1e-9


def format_axis_number(value: float) -> str:
    """Chart axis label: grouped integer when whole, else two decimals; negatives take U+2212."""
    sign = _MINUS if value < 0 else ""
    magnitude = abs(value)
    rounded = round(magnitude)
    if abs(magnitude - rounded) < _INT_LABEL_EPSILON:
        return f"{sign}{int(rounded):,}"
    return f"{sign}{magnitude:,.2f}"


def percent_of(part_minor: int, total_minor: int) -> int:
    """Whole percent ``part / total`` (floored; 0 when ``total_minor`` is not positive)."""
    if total_minor <= 0:
        return 0
    return part_minor * 100 // total_minor


def format_major(amount_minor: int, currency: str, *, grouped: bool = False) -> str:
    """Bare major-unit decimal at the currency exponent, for edit forms.

    ``grouped`` separates thousands with commas (``2,239.80``, the handoff dialogs; the amount
    parser reads it back). A currency without decimals stays bare: ``1,234`` would read as 1.234.
    """
    decimals = currency_decimals(currency)
    value = minor_to_major(amount_minor, currency)
    if grouped and decimals > 0:
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"


def format_whole(amount_minor: int, currency: str, *, grouped: bool = True) -> str:
    """Whole major units (ties to even), for dense tables; sign preserved, never ``-0``."""
    value = Decimal(round_scaled(minor_to_major(amount_minor, currency)))
    if value == 0:
        value = Decimal(0)
    return format(value, ",.0f" if grouped else ".0f")


def format_bps_percent(bps: int) -> str:
    """Basis points as a two-decimal percent string (1 -> ``'0.01'``)."""
    return f"{bps_to_percent(bps):.2f}"


_PERCENT_RE: Final = re.compile(r"[+-]?\d{1,9}(?:\.\d{1,9})?", re.ASCII)


def parse_percent_str(raw: str) -> Decimal | None:
    """Parse percent text (``"12"``, ``"12,5"``) to a Decimal, or ``None``."""
    normalised = raw.strip().replace(",", ".")
    return Decimal(normalised) if _PERCENT_RE.fullmatch(normalised) else None


def percent_to_bps(percent: Decimal) -> int:
    """Percent ``Decimal`` as whole basis points, rounded ties to even."""
    return round_scaled(percent * _BPS_PER_PERCENT)


def major_float(amount_minor: int, currency: str) -> float:
    """Major-unit float for chart geometry only (never for stored or displayed money)."""
    return float(minor_to_major(amount_minor, currency))


def divide_minor_units(amount_minor: int, parts: int) -> int:
    """Split ``amount_minor`` into ``parts`` equal shares, rounding toward negative infinity.

    The single integer-division rounding point for money; T-Q216 owns the final
    rounding policy.
    """
    return amount_minor // parts


def rescale_minor(amount_minor: int, from_ccy: str, to_ccy: str, rate: Decimal) -> int:
    """Re-express ``amount_minor`` of ``from_ccy`` in ``to_ccy`` minor units at ``rate``.

    The single FX rounding point (ADR-0139): scale by both currency exponents,
    multiply by the rate, round half to even. Sign is preserved.
    """
    major = Decimal(amount_minor) / (Decimal(10) ** currency_decimals(from_ccy))
    scaled = major * rate * (Decimal(10) ** currency_decimals(to_ccy))
    return round_scaled(scaled)
