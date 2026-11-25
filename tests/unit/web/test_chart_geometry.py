"""Geometry of the Rising Dough forecast and income-vs-expense charts (T-UR12)."""

from __future__ import annotations

import datetime as dt

from budget_planner.services.analytics import MonthlyFlow
from budget_planner.services.forecast import MonthlyProjectionPoint
from budget_planner.web.chart_geometry import flow_chart, forecast_chart

MINUS = "\N{MINUS SIGN}"


def _series(balances: list[int], net: int = 0) -> tuple[MonthlyProjectionPoint, ...]:
    return tuple(
        MonthlyProjectionPoint(
            month=dt.date(2026 + (9 + i) // 12, (9 + i) % 12 + 1, 1),
            label="x",
            end_balance_minor=b,
            net_minor=net,
        )
        for i, b in enumerate(balances)
    )


def test_twelve_months_sit_98_px_apart_inside_the_8_px_inset() -> None:
    chart = forecast_chart(_series([1_000_00 * i for i in range(1, 13)]), "PLN", caption_prefix="P")

    xs = [d.x for d in chart.dots]
    assert xs[0] == "72.000"
    assert xs[1] == "170.000"
    assert xs[-1] == "1150.000"
    assert len(chart.ticks) == 12


def test_axis_is_the_nice_scale_of_the_balances() -> None:
    chart = forecast_chart(_series([3_272_722, 8_623_967]), "PLN", caption_prefix="P")

    assert [g.label for g in chart.grid] == ["20,000", "40,000", "60,000", "80,000", "100,000"]
    assert chart.grid[0].y == "262.000"
    assert chart.grid[-1].y == "16.000"


def test_tooltip_sits_above_the_point_and_flips_below_when_it_would_clip_the_top() -> None:
    chart = forecast_chart(_series([3_272_722, 8_101_351, 8_623_967]), "PLN", caption_prefix="P")

    low, high = chart.dots[0].tooltip, chart.dots[2].tooltip
    assert float(low.y) < float(chart.dots[0].y)  # above
    assert float(high.y) > float(chart.dots[2].y)  # flipped below: 14 px under the point
    assert (high.width, high.height) == ("190", "64")


def test_tooltip_is_clamped_to_the_view_box() -> None:
    chart = forecast_chart(_series([100, 200, 300]), "PLN", caption_prefix="P")

    assert chart.dots[0].tooltip.x == "0.000"
    assert chart.dots[-1].tooltip.x == "994.000"  # 1184 - 190


def test_negative_balance_and_net_use_the_minus_sign() -> None:
    chart = forecast_chart(_series([-210_000], net=-30_000), "PLN", caption_prefix="P")

    assert chart.dots[0].aria_label == f"Oct 2026: {MINUS}2,100.00 PLN, net {MINUS}300.00"
    assert chart.dots[0].tooltip.detail == f"net {MINUS}300.00"


def test_sixty_months_label_every_third_month_and_keep_all_ticks() -> None:
    chart = forecast_chart(_series([i * 100_00 for i in range(60)]), "PLN", caption_prefix="P")

    labelled = [t.month for t in chart.ticks if t.month]
    assert len(chart.ticks) == 60
    assert len(labelled) == 20
    assert chart.ticks[0].month == "OCT"
    assert chart.ticks[1].month == ""


def test_a_single_month_sits_mid_plot_and_no_month_draws_an_empty_chart() -> None:
    single = forecast_chart(_series([5_000_00]), "PLN", caption_prefix="P")
    empty = forecast_chart((), "PLN", caption_prefix="P")

    assert single.dots[0].x == "611.000"
    assert empty.dots == () and empty.line_points == "" and empty.grid == ()
    assert empty.aria_label == "Projected balance by month: no data."


def _flows(
    count: int, income: int = 2_000_000, expense: int = 1_000_000
) -> tuple[MonthlyFlow, ...]:
    return tuple(
        MonthlyFlow(2026 if i < 12 else 2027, i % 12 + 1, income, expense) for i in range(count)
    )


def test_four_months_use_the_boards_slots() -> None:
    chart = flow_chart(_flows(4), "PLN", current=(2026, 4))

    assert [m.band_x for m in chart.months] == ["60.000", "176.000", "292.000", "408.000"]
    assert chart.months[0].band_width == "108.000"
    assert [g.label for g in chart.grid] == ["0k", "5k", "10k", "15k", "20k"]
    assert [lo.is_now for lo in chart.months[3].loaves] == [True, True]
    assert [lo.is_now for lo in chart.months[0].loaves] == [False, False]
    assert [lo.is_expense for lo in chart.months[0].loaves] == [False, True]


def test_twelve_months_shrink_to_fit_the_plot() -> None:
    chart = flow_chart(_flows(12), "PLN", current=(2026, 12))

    last = chart.months[-1]
    assert float(last.band_x) + float(last.band_width) <= 520.0
    assert float(chart.months[1].band_x) - float(chart.months[0].band_x) < 40


def test_a_zero_amount_draws_no_loaf_and_a_tiny_one_keeps_its_base() -> None:
    zero = flow_chart((MonthlyFlow(2026, 1, 0, 5_000_00),), "PLN", current=(2026, 1))
    tiny = flow_chart((MonthlyFlow(2026, 1, 1, 5_000_00),), "PLN", current=(2026, 1))

    assert zero.months[0].loaves[0].d == ""
    assert zero.months[0].loaves[1].d != ""
    assert "L" in tiny.months[0].loaves[0].d
    assert tiny.months[0].loaves[0].d.count("246.000") >= 1  # arc starts no lower than the base


def test_month_aria_label_tooltip_and_span_across_a_year() -> None:
    months = (MonthlyFlow(2025, 12, 100_000, 250_000), MonthlyFlow(2026, 1, 300_000, 100_000))

    chart = flow_chart(months, "PLN", current=(2026, 1))

    assert chart.months[0].aria_label == "Dec 2025: income 1,000.00 PLN, expense 2,500.00 PLN"
    assert chart.months[0].tooltip.value == "in 1,000.00 \N{MIDDLE DOT} out 2,500.00"
    assert chart.months[0].tooltip.detail == f"net {MINUS}1,500.00"
    assert chart.months[1].tooltip.detail == "net +2,000.00"
    assert chart.aria_label.startswith("Monthly income and expense, Dec 2025 to Jan 2026.")


def test_no_months_draws_an_empty_chart() -> None:
    chart = flow_chart((), "PLN", current=(2026, 1))

    assert chart.months == () and chart.grid == ()
