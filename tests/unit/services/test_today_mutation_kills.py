"""Mutation-kill tests for ``services/today`` (T-Q247, ADR-0131).

``afford`` is a pure read over the budget summary, so the summary is stubbed to pin exact arithmetic
(HALF_EVEN rounding, the 50% tight threshold, floors) and the arguments forwarded to
``services.budget``.
Complements ``test_today_afford.py``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from budget_planner.services import budget as budget_service, today as today_svc

USER_ID = 7
TODAY = date(2026, 11, 12)


@dataclass
class _Calls:
    fiscal: list[tuple[int, date]]
    summary: list[tuple[int, int, int, date, str]]


def _stub_summary(monkeypatch: pytest.MonkeyPatch, *, remaining: int, days_left: int) -> _Calls:
    calls = _Calls([], [])

    def fiscal_month_for(_conn: object, user_id: int, today: date) -> tuple[int, int]:
        calls.fiscal.append((user_id, today))
        return 2026, 10

    def month_summary(
        _conn: object, user_id: int, year: int, month: int, *, today: date, base_currency: str
    ) -> SimpleNamespace:
        calls.summary.append((user_id, year, month, today, base_currency))
        return SimpleNamespace(
            days_until_next_income=days_left, totals=SimpleNamespace(remaining_minor=remaining)
        )

    monkeypatch.setattr(budget_service, "fiscal_month_for", fiscal_month_for)
    monkeypatch.setattr(budget_service, "month_summary", month_summary)
    return calls


def _afford(conn: sqlite3.Connection, amount: int) -> today_svc.AffordResult:
    return today_svc.afford(conn, USER_ID, TODAY, amount, base_currency="PLN")


@pytest.mark.parametrize(
    ("remaining", "days", "expected"),
    [
        (100, 3, 33),
        (101, 2, 50),  # 50.5 -> half-even 50
        (103, 2, 52),  # 51.5 -> half-even 52
        (-100, 3, -33),  # not clamped
        (-101, 2, -50),
        (100, 0, 100),  # days floored at 1
        (100, -5, 100),
        (100, 1, 100),
        (100, 2, 50),
        (0, 4, 0),
    ],
)
def test_daily_share_minor(remaining: int, days: int, expected: int) -> None:
    assert today_svc.daily_share_minor(remaining, days) == expected


def test_afford_forwards_user_and_today_to_the_budget_service(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_summary(monkeypatch, remaining=10_000, days_left=10)
    _afford(conn, 0)
    assert calls.fiscal == [(USER_ID, TODAY)]
    assert calls.summary == [(USER_ID, 2026, 10, TODAY, "PLN")]


def test_afford_exact_values(conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_summary(monkeypatch, remaining=10_000, days_left=10)
    assert _afford(conn, 0) == today_svc.AffordResult(
        per_day_minor=1_000, delta_minor=0, pace_tag="on_track", days_left=10
    )
    assert _afford(conn, 2_500) == today_svc.AffordResult(
        per_day_minor=750, delta_minor=-250, pace_tag="on_track", days_left=10
    )


def test_pace_tag_boundaries_around_half_of_baseline(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_summary(monkeypatch, remaining=10_000, days_left=10)  # baseline 1_000/day, threshold 500
    assert _afford(conn, 5_000).pace_tag == "on_track"  # exactly 500: not strictly below
    assert _afford(conn, 5_010).pace_tag == "tight"  # 499
    assert _afford(conn, 9_990).pace_tag == "tight"  # 1/day is tight, not over_limit
    assert _afford(conn, 9_999).pace_tag == "over_limit"  # 0.1 rounds to 0
    assert _afford(conn, 10_000).pace_tag == "over_limit"


def test_afford_rounds_half_even_at_per_day(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_summary(monkeypatch, remaining=105, days_left=2)  # 52.5 -> 52
    first = _afford(conn, 0)
    assert (first.per_day_minor, first.delta_minor) == (52, 0)
    second = _afford(conn, 2)  # 103 / 2 = 51.5 -> 52
    assert (second.per_day_minor, second.delta_minor) == (52, 0)


def test_days_left_floor_and_clamps(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_summary(monkeypatch, remaining=900, days_left=0)
    zero_days = _afford(conn, 0)
    assert (zero_days.days_left, zero_days.per_day_minor) == (1, 900)
    _stub_summary(monkeypatch, remaining=100, days_left=1)
    overspend = _afford(conn, 500)  # remaining clamps at 0, not 1
    assert (overspend.per_day_minor, overspend.delta_minor, overspend.pace_tag) == (
        0,
        -100,
        "over_limit",
    )
    _stub_summary(monkeypatch, remaining=-50, days_left=1)  # negative remaining clamps at 0
    negative = _afford(conn, 0)
    assert (negative.per_day_minor, negative.delta_minor, negative.pace_tag) == (
        0,
        0,
        "over_limit",
    )


def test_negative_amount_is_rejected_with_message(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_summary(monkeypatch, remaining=100, days_left=1)
    with pytest.raises(ValueError, match=r"^amount_minor must be non-negative$"):
        _afford(conn, -1)
    assert _afford(conn, 0).per_day_minor == 100  # zero is allowed


def test_tight_threshold_is_exactly_half_of_the_baseline(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_summary(monkeypatch, remaining=1_000_000, days_left=10)  # baseline 100_000/day
    assert _afford(conn, 500_000).pace_tag == "on_track"  # 50_000 = half
    assert _afford(conn, 500_030).pace_tag == "tight"  # 49_997, within 0.01% of half
    assert _afford(conn, 499_970).pace_tag == "on_track"  # 50_003
