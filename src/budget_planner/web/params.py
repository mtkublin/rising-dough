"""Request parameter parsing: query/form/path text to typed values (T-Q233, Q-023).

Pure functions. Lenient parsers (``parse_date``, ``parse_int``) return ``None`` for text they
cannot accept; they serve form fields whose callers report their own field error. A malformed
*query* parameter is never silently dropped (ADR-0141 amendment 2026-11-22, T-Q282): the
``query_*`` helpers and ``parse_year_month`` raise ``ParamError`` (a visible 422) for a present
but invalid value, while an absent or empty one is ``None`` or the caller's default. Amount text
is parsed by ``domain.money.parse_amount_str`` / ``parse_amount_minor``, not here.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Final

from budget_planner.domain.limits import ID_MAX
from budget_planner.domain.money import (
    format_figure,
    parse_amount_minor,
    parse_amount_str,
    to_minor_units,
)

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


def query_date(name: str, value: str | None) -> date | None:
    """Query ``YYYY-MM-DD``: absent or empty is ``None``, malformed raises ``ParamError``."""
    if not value:
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise ParamError({name: f"{name} must be a date like 2026-01-31"})
    return parsed


def query_int(
    name: str,
    value: str | None,
    *,
    minimum: int | None = None,
    maximum: int | None = ID_MAX,
    choices: tuple[int, ...] | None = None,
) -> int | None:
    """Query integer: absent or empty is ``None``; bad, out of range or off-``choices`` raises."""
    if value is None or value.strip() == "":
        return None
    number = parse_int(value, minimum=minimum, maximum=maximum)
    if number is None or (choices is not None and number not in choices):
        raise ParamError({name: _int_message(name, minimum, maximum, choices)})
    return number


def _int_message(
    name: str, minimum: int | None, maximum: int | None, choices: tuple[int, ...] | None
) -> str:
    if choices is not None:
        return f"{name} must be one of {', '.join(str(c) for c in choices)}"
    if minimum is not None and maximum is not None:
        return f"{name} must be a whole number between {minimum} and {maximum}"
    return f"{name} must be a whole number"


EXPORT_FORMATS: Final = ("csv", "parquet")


def query_choice[T: str](name: str, value: str | None, choices: tuple[T, ...]) -> T | None:
    """Query choice: absent or empty is ``None``; a value outside ``choices`` raises."""
    if value is None or value == "":
        return None
    for choice in choices:
        if choice == value:
            return choice
    raise ParamError({name: f"{name} must be one of {', '.join(choices)}"})


def require_year_month(year_raw: str | None, month_raw: str | None) -> None:
    """Raise ``ParamError`` when a present ``year`` or ``month`` text is malformed."""
    parse_year_month(year_raw, month_raw, (MIN_YEAR, 1))


def parse_year_month(
    year_raw: str | None, month_raw: str | None, fallback: tuple[int, int]
) -> tuple[int, int]:
    """Year and month from raw text; absent takes ``fallback``, bad raises ``ParamError``."""
    year = fallback[0] if not year_raw else parse_int(year_raw, minimum=MIN_YEAR, maximum=MAX_YEAR)
    month = (
        fallback[1] if not month_raw else parse_int(month_raw, minimum=1, maximum=_MONTHS_IN_YEAR)
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
        return None, f"Enter an amount above {format_figure(0, currency)}"
    return to_minor_units(dec, currency), None


def credit_limit_amount(raw: str, currency: str) -> tuple[int | None, str | None]:
    """Positive credit limit text to ``(minor, None)`` or ``(None, error message)``."""
    minor = parse_amount_minor(raw, currency) if raw.strip() else None
    if minor is None or minor <= 0:
        return None, "positive credit limit required"
    return minor, None
