"""Money helpers.

Amounts are stored as signed integer minor units of the account currency
(ADR-0008 / ADR-0006). All conversion between major-unit ``Decimal`` and
integer minor units routes through this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final, Literal

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

# Rounding policy (ADR-0006 amendment 2026-11-21, ADR-0140): the mode is an explicit
# argument of the two helpers below; call sites keep the mode they always had.
RoundingMode = Literal["ROUND_HALF_EVEN", "ROUND_HALF_UP"]
HALF_EVEN: Final[RoundingMode] = "ROUND_HALF_EVEN"
HALF_UP: Final[RoundingMode] = "ROUND_HALF_UP"
_ONE: Final = Decimal(1)


def round_scaled(value: Decimal, *, mode: RoundingMode) -> int:
    """Round a ``Decimal`` to the nearest integer using ``mode`` (the one quantize point)."""
    return int(value.quantize(_ONE, rounding=mode))


def round_div(numerator: int, denominator: int, *, mode: RoundingMode) -> int:
    """Integer ratio ``numerator / denominator`` rounded to the nearest integer using ``mode``."""
    return round_scaled(Decimal(numerator) / Decimal(denominator), mode=mode)


_BPS_PER_PERCENT: Final = Decimal(100)


def mean_minor(total_minor: int, count: int) -> int:
    """Mean of ``total_minor`` over ``count`` items, half-even; 0 when ``count <= 0``."""
    if count <= 0:
        return 0
    return round_div(total_minor, count, mode=HALF_EVEN)


def currency_decimals(currency: str) -> int:
    """Return the ISO 4217 minor-unit exponent for ``currency`` (2 for unknown codes)."""
    return CURRENCY_EXPONENTS.get(currency.upper(), _DEFAULT_EXPONENT)


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal major-unit amount to signed integer minor units.

    Uses banker's-safe ROUND_HALF_UP (consistent with user expectations in
    finance UIs). Does not clamp the magnitude.
    """
    decimals = currency_decimals(currency)
    quant = Decimal(10) ** -decimals
    quantised = amount.quantize(quant, rounding=HALF_UP)
    return int(quantised * (Decimal(10) ** decimals))


def parse_amount_str(raw: str, currency: str) -> Decimal | None:
    """Parse a user-entered amount string into a Decimal (T-124 / ADR-0040).

    - Normalises comma to dot so Polish/EU-style ``12,34`` and dot-style
      ``12.34`` both round-trip to the same minor-unit value.
    - Rejects more fractional digits than the currency supports (e.g.
      ``12.345`` for PLN) by returning ``None``; the router surfaces a 422
      with the same inline error shape as other invalid-amount cases.
    - Rejects non-decimal strings and non-finite values by returning ``None``.

    Mirrors ``numeric-input.js`` which already allows either separator in
    the UI; this helper pins the server contract against future
    regressions.
    """
    normalised = raw.strip().replace(",", ".")
    if not normalised:
        return None
    try:
        dec = Decimal(normalised)
    except (InvalidOperation, ValueError):
        return None
    if not dec.is_finite():
        return None
    _, _, frac = normalised.partition(".")
    if len(frac) > currency_decimals(currency):
        return None
    return dec


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


def bps_to_percent(bps: int) -> Decimal:
    """Basis points as a percent ``Decimal`` (150 -> 1.5); not a currency amount."""
    return Decimal(bps) / _BPS_PER_PERCENT


_INT_LABEL_EPSILON: Final = 1e-9


def format_axis_number(value: float) -> str:
    """Chart axis label: grouped integer when whole, else two decimals."""
    rounded = round(value)
    if abs(value - rounded) < _INT_LABEL_EPSILON:
        return f"{int(rounded):,}"
    return f"{value:,.2f}"


def percent_of(part_minor: int, total_minor: int) -> int:
    """Whole percent ``part / total`` (floored; 0 when ``total_minor`` is not positive)."""
    if total_minor <= 0:
        return 0
    return part_minor * 100 // total_minor


def format_major(amount_minor: int, currency: str) -> str:
    """Bare major-unit decimal at the currency exponent, for edit forms."""
    decimals = currency_decimals(currency)
    return f"{minor_to_major(amount_minor, currency):.{decimals}f}"


def format_whole(amount_minor: int, currency: str, *, grouped: bool = True) -> str:
    """Whole major units (half up), for dense tables; sign preserved, never ``-0``."""
    value = Decimal(round_scaled(minor_to_major(amount_minor, currency), mode=HALF_UP))
    if value == 0:
        value = Decimal(0)
    return format(value, ",.0f" if grouped else ".0f")


def format_bps_percent(bps: int) -> str:
    """Basis points as a two-decimal percent string (1 -> ``'0.01'``)."""
    return f"{bps_to_percent(bps):.2f}"


def percent_to_bps(percent: Decimal) -> int:
    """Percent ``Decimal`` as whole basis points, rounded half up."""
    return round_scaled(percent * _BPS_PER_PERCENT, mode=HALF_UP)


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
    return round_scaled(scaled, mode=HALF_EVEN)
