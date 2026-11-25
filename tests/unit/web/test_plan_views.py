"""Forecast hero note, horizon buttons and analytics rows of the Plan pages (T-UR12)."""

from __future__ import annotations

import datetime as dt

from budget_planner.services.analytics import AnalyticsBundle, CategoryTotal
from budget_planner.services.forecast import (
    MonthlyProjectionPoint,
    TrendDirection,
    projection_summary,
)
from budget_planner.web.plan_views import forecast_hero_note, forecast_page, spend_rows

MINUS = "\N{MINUS SIGN}"
DOT = "\N{MIDDLE DOT}"


def _point(month: int, balance: int, net: int = 0) -> MonthlyProjectionPoint:
    return MonthlyProjectionPoint(
        month=dt.date(2026, month, 1), label="x", end_balance_minor=balance, net_minor=net
    )


def test_hero_note_signs_the_delta_and_names_the_peak() -> None:
    points = (_point(10, 90_00), _point(11, 150_00), _point(12, 120_00))

    up = projection_summary(points, now_value=100_00)
    down = projection_summary(points, now_value=500_00)
    flat = projection_summary(points, now_value=120_00)

    assert up is not None and down is not None and flat is not None
    assert up.delta_direction is TrendDirection.UP
    assert (
        forecast_hero_note(up, "PLN") == f"+20.00 PLN over 3 months {DOT} peak 150.00 in nov 2026"
    )
    assert forecast_hero_note(down, "PLN") == (
        f"{MINUS}380.00 PLN over 3 months {DOT} peak 150.00 in nov 2026"
    )
    assert forecast_hero_note(flat, "PLN").startswith("0.00 PLN over 3 months")


def test_one_month_horizon_is_singular() -> None:
    summary = projection_summary((_point(10, 50_00),), now_value=0)

    assert summary is not None
    assert (
        forecast_hero_note(summary, "PLN")
        == f"+50.00 PLN over 1 month {DOT} peak 50.00 in oct 2026"
    )


def test_forecast_page_marks_the_pressed_horizon_and_the_negative_net() -> None:
    points = (_point(10, 90_00, net=-10_00), _point(11, 150_00, net=60_00))
    summary = projection_summary(points, now_value=100_00)

    page = forecast_page(
        points,
        summary,
        horizon=12,
        choices=(6, 12),
        currency="PLN",
        base_url="/plan?tab=forecast&horizon=",
    )

    assert page.hero_label == f"projected balance {DOT} end of nov 2026"
    assert page.hero_balance_minor == 150_00
    assert [(o.months, o.pressed, o.url) for o in page.options] == [
        (6, False, "/plan?tab=forecast&horizon=6"),
        (12, True, "/plan?tab=forecast&horizon=12"),
    ]
    assert [(r.net_text, r.net_negative) for r in page.rows] == [
        (f"{MINUS}10.00", True),
        ("60.00", False),
    ]


def test_forecast_page_without_a_projection_has_a_plain_hero() -> None:
    page = forecast_page(
        (), None, horizon=12, choices=(12,), currency="PLN", base_url="/plan?tab=forecast&horizon="
    )

    assert (page.hero_label, page.hero_balance_minor, page.hero_note) == (
        "projected balance",
        0,
        "",
    )
    assert page.rows == ()


def _bundle(rows: tuple[tuple[int, str, int], ...]) -> AnalyticsBundle:
    return AnalyticsBundle(
        period="month",
        period_start=dt.date(2026, 10, 1),
        period_end=dt.date(2026, 10, 31),
        spend_by_category=tuple(CategoryTotal(i, n, a) for i, n, a in rows),
        twelve_month_averages=(),
        income_vs_expense_monthly=(),
        largest_items=(),
    )


def test_spend_rows_share_bar_and_deltas() -> None:
    bundle = _bundle(
        ((1, "Taxes", 5_000_00), (2, "Car", 4_000_00), (3, "Tiny", 1_00), (4, "Even", 999_00))
    )

    rows = spend_rows(bundle, {1: 4_000_00, 2: 5_000_00, 4: 999_00}, {1: "#aabbcc"}, "PLN")

    by_name = {r.category_name: r for r in rows}
    assert by_name["Taxes"].share_pct == 50
    assert by_name["Taxes"].bar_filled == "\u2588" * 10
    assert by_name["Taxes"].bar_rest == "\u2591" * 10
    assert by_name["Taxes"].delta_text == "\u25b2 +1,000.00" and not by_name["Taxes"].delta_down
    assert by_name["Car"].delta_text == f"\u25bc {MINUS}1,000.00" and by_name["Car"].delta_down
    assert by_name["Tiny"].share_pct == 0
    assert by_name["Tiny"].bar_filled == "\u2588"  # a non-zero amount keeps one cell
    assert by_name["Tiny"].delta_text == "\u2014" and not by_name["Tiny"].has_average
    assert by_name["Even"].share_pct == 9
    assert by_name["Even"].delta_text == "\u2014"  # equal to its average: no delta
    assert by_name["Taxes"].category_color == "#aabbcc" and by_name["Car"].category_color is None
    assert by_name["Taxes"].ledger_url == (
        "/ledger?view=actual&category_id=1&date_from=2026-10-01&date_to=2026-10-31"
    )
    assert by_name["Taxes"].link_label == "Taxes: 5,000.00 PLN, open in ledger"


def test_negative_balance_text_uses_the_minus_sign() -> None:
    points = (_point(10, -18_830_45), _point(11, 5_00))

    page = forecast_page(
        points,
        None,
        horizon=6,
        choices=(6,),
        currency="PLN",
        base_url="/plan?tab=forecast&horizon=",
    )

    assert [r.balance_text for r in page.rows] == [f"{MINUS}18,830.45", "5.00"]
