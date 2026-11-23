"""Today services — pure helpers behind the `/today` surface (ADR-0056 §3).

The ``afford`` helper is a pure read over the shared ``services.budget``
summary: no DB write, deterministic for a fixed ``today``. Used by the Can-I-
afford live preview (debounced HTMX fragment) + any future "simulate a
transaction" UI.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Literal

from budget_planner.domain.money import round_div
from budget_planner.services import budget as budget_service

PaceTag = Literal["on_track", "tight", "over_limit"]

# Shown for an empty, zero, negative or unparseable amount (handoff afford-invalid).
AFFORD_INVALID_MESSAGE = "Enter an amount, like 250.00"


@dataclass(frozen=True, slots=True)
class AffordResult:
    """Result of :func:`afford` — recomputed per-day figure + delta + pace.

    ``per_day_minor`` is clamped at zero; ``delta_minor`` is signed
    (negative = user would spend less per day after the proposed amount,
    positive = would end up with more headroom). ``days_left`` surfaces
    the days-until-next-income used for the division so the UI can show
    the window verbatim. ``unclamped_per_day_minor`` is the same per-day
    figure without the zero floor (negative when the entry exceeds what is
    left; the value the handoff "per day becomes -x" line shows).
    ``over_minor`` is how much the entry exceeds what is left, in positive
    minor units (0 when it fits).
    """

    per_day_minor: int
    delta_minor: int
    pace_tag: PaceTag
    days_left: int
    unclamped_per_day_minor: int = 0
    over_minor: int = 0


# Boundary at which the recomputed per-day drops below a "tight" threshold.
# Treats "half of the current left-per-day" as the handoff between on_track
# and tight; zero after the hypothetical spend lands on over_limit. Keeps the
# tag deterministic for a given summary without a new preference.
_TIGHT_FRACTION_BPS = 5_000  # 50% of baseline, in basis points.
_FULL_BPS = 10_000  # 100% in basis points.


def _div_round_half_even(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round_div(numerator, denominator)


def _pace_tag_for(
    per_day_minor: int,
    baseline_per_day_minor: int,
) -> PaceTag:
    """Map ``per_day_minor`` into one of three pace tags.

    - ``over_limit`` when the hypothetical per-day drops to zero (either
      because the user has no budget headroom or the proposed amount
      wipes it out).
    - ``tight`` when the new per-day is strictly below half the current
      baseline (``_TIGHT_FRACTION_BPS``).
    - ``on_track`` otherwise.
    """
    if per_day_minor <= 0:
        return "over_limit"
    if baseline_per_day_minor <= 0:
        return "on_track"
    if per_day_minor * _FULL_BPS < baseline_per_day_minor * _TIGHT_FRACTION_BPS:
        return "tight"
    return "on_track"


def daily_share_minor(remaining_minor: int, days_left: int) -> int:
    """Per-day share of ``remaining_minor`` (not clamped), same rounding as :func:`afford`."""
    return _div_round_half_even(remaining_minor, max(days_left, 1))


def afford(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    amount_minor: int,
    *,
    base_currency: str,
    display_timezone: str,
) -> AffordResult:
    """Return the recomputed per-day figure for a hypothetical spend.

    ``amount_minor`` is non-negative. Validation of the sign happens at the
    router boundary (422 on negative). This helper never writes.
    """
    if amount_minor < 0:
        raise ValueError("amount_minor must be non-negative")

    # ADR-0064: resolve fiscal month so the baseline matches the Today hero's
    # left-per-day. Using today.year/today.month pulls the wrong cycle when
    # today falls before the current calendar month's anchor paycheck.
    year, month = budget_service.fiscal_month_for(conn, user_id, today)
    summary = budget_service.month_summary(
        conn,
        user_id,
        year,
        month,
        today=today,
        base_currency=base_currency,
        display_timezone=display_timezone,
    )
    days_left = max(summary.days_until_next_income, 1)
    raw_remaining_minor = summary.totals.remaining_minor
    remaining_minor = max(raw_remaining_minor, 0)
    baseline_per_day = _div_round_half_even(remaining_minor, days_left)

    new_remaining = remaining_minor - amount_minor
    new_remaining = max(new_remaining, 0)
    per_day = _div_round_half_even(new_remaining, days_left)
    delta = per_day - baseline_per_day
    tag = _pace_tag_for(per_day, baseline_per_day)
    return AffordResult(
        per_day_minor=per_day,
        delta_minor=delta,
        pace_tag=tag,
        days_left=days_left,
        unclamped_per_day_minor=daily_share_minor(raw_remaining_minor - amount_minor, days_left),
        over_minor=max(amount_minor - remaining_minor, 0),
    )


__all__ = [
    "AFFORD_INVALID_MESSAGE",
    "AffordResult",
    "PaceTag",
    "afford",
    "daily_share_minor",
]
