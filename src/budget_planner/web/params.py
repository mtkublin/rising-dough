"""Request parameter parsing: query/form/path text to typed values (T-Q233, Q-023).

Pure functions. Lenient parsers (``parse_date``, ``parse_int``) return ``None`` for text they
cannot accept so list filters degrade to "no filter"; the strict helpers raise
``domain.errors.ValidationError`` so a bad value is a visible 422, never a 500. Amount text is
parsed by ``domain.money.parse_amount_str`` / ``parse_amount_minor``, not here.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Final

from budget_planner.domain.limits import ID_MAX
from budget_planner.domain.money import parse_amount_minor, parse_amount_str, to_minor_units

logger = logging.getLogger(__name__)
MIN_YEAR: Final = date.min.year
MAX_YEAR: Final = date.max.year
_MONTHS_IN_YEAR: Final = 12
_INT_RE: Final = re.compile(r"[+-]?\d{1,19}", re.ASCII)


class ParamError(Exception):
    """A request parameter is malformed or out of range; the app maps it to a visible 422.

    A plain (non-frozen) exception on purpose: it is raised inside ``yield`` dependencies' scope.
    """

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in fields.items()))
        self.fields = fields


def parse_date(value: str | None) -> date | None:
    """ISO ``YYYY-MM-DD`` to a date; ``None`` for empty or invalid text."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.debug("ignoring unparseable date parameter")
        return None


def parse_int(
    value: str | None, *, minimum: int | None = None, maximum: int | None = ID_MAX
) -> int | None:
    """ASCII integer within ``[minimum, maximum]`` (default up to ``ID_MAX``), else ``None``."""
    if value is None:
        return None
    text = value.strip()
    if not _INT_RE.fullmatch(text):
        return None
    number = int(text)
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        return None
    return number


def parse_year_month(
    year_raw: str | None, month_raw: str | None, fallback: tuple[int, int]
) -> tuple[int, int]:
    """Year and month from raw text; absent takes ``fallback``, bad raises ``ParamError``."""
    year = (
        fallback[0] if year_raw is None else parse_int(year_raw, minimum=MIN_YEAR, maximum=MAX_YEAR)
    )
    month = (
        fallback[1]
        if month_raw is None
        else parse_int(month_raw, minimum=1, maximum=_MONTHS_IN_YEAR)
    )
    if year is not None and month is not None:
        return year, month
    fields: dict[str, str] = {}
    if year is None:
        fields["year"] = f"year must be between {MIN_YEAR} and {MAX_YEAR}"
    if month is None:
        fields["month"] = "month must be between 1 and 12"
    raise ParamError(fields)


def positive_amount(raw: str, currency: str) -> tuple[int | None, str | None]:
    """Strictly positive amount text to ``(minor_units, None)`` or ``(None, error message)``."""
    dec = parse_amount_str(raw, currency)
    if dec is None:
        return None, "amount must be a decimal number within range"
    if dec <= 0:
        return None, "amount must be positive"
    return to_minor_units(dec, currency), None


def afford_amount_minor(raw: str, currency: str) -> int | None:
    """``amount=`` query text to minor units; blank is 0, invalid or out of range is ``None``."""
    stripped = (raw or "").strip()
    return 0 if stripped == "" else parse_amount_minor(stripped, currency)


def credit_limit_amount(raw: str, currency: str) -> tuple[int | None, str | None]:
    """Positive credit limit text to ``(minor, None)`` or ``(None, error message)``."""
    minor = parse_amount_minor(raw, currency) if raw.strip() else None
    if minor is None or minor <= 0:
        return None, "positive credit limit required"
    return minor, None
