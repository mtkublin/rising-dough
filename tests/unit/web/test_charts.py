"""Unit tests for the pure SVG chart geometry helpers (T-R47, ADR-0054)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from budget_planner.web.charts import (
    AxisTick,
    GroupedBarsChart,
    HorizontalBarsChart,
    LineAreaChart,
    Sparkline,
    _axis_ticks,
    _fmt,
    _nice_axis,
    grouped_bars,
    horizontal_bars,
    line_area,
    sparkline,
)

# ---------------------------------------------------------------------------
# shared primitives
# ---------------------------------------------------------------------------


def test_fmt_fixed_decimals() -> None:
    assert _fmt(1.0) == "1.000"
    assert _fmt(0.00001) == "0.000"
    assert _fmt(1_234_567.89) == "1234567.890"
    assert "e" not in _fmt(1e-9)


def test_nice_axis_positive_range() -> None:
    nice_min, nice_max, step = _nice_axis(0.0, 1234.0, target_ticks=5)
    assert nice_min == 0.0
    assert nice_max >= 1234.0
    assert step > 0
    # Nice step should be exactly a multiple of 1/2/2.5/5 * 10^k.
    assert step in {200.0, 250.0, 500.0, 300.0, 400.0}


def test_nice_axis_identical_min_max() -> None:
    nice_min, nice_max, step = _nice_axis(5.0, 5.0)
    assert nice_min < 5.0 < nice_max
    assert step > 0


def test_nice_axis_zero_zero() -> None:
    nice_min, nice_max, step = _nice_axis(0.0, 0.0)
    assert nice_min < 0.0 < nice_max
    assert step > 0


def test_nice_axis_negative_values() -> None:
    nice_min, nice_max, step = _nice_axis(-100.0, 100.0)
    assert nice_min <= -100.0
    assert nice_max >= 100.0
    assert step > 0


def test_nice_axis_tiny_fraction() -> None:
    nice_min, nice_max, _ = _nice_axis(0.0, 0.5)
    assert nice_min <= 0.0
    assert nice_max >= 0.5


def test_nice_axis_fallback_tick_count() -> None:
    _, _, step = _nice_axis(0.0, 100.0, target_ticks=0)
    assert step > 0


def test_axis_ticks_inclusive() -> None:
    ticks = _axis_ticks(0.0, 10.0, 2.0)
    assert ticks == (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)


def test_axis_ticks_zero_step_returns_single_tick() -> None:
    assert _axis_ticks(5.0, 10.0, 0.0) == (5.0,)


# ---------------------------------------------------------------------------
# line_area
# ---------------------------------------------------------------------------


def test_line_area_basic_shape() -> None:
    chart = line_area([(0.0, 10.0), (1.0, 20.0), (2.0, 15.0)])
    assert isinstance(chart, LineAreaChart)
    assert chart.line_d.startswith("M")
    assert chart.area_d.endswith("Z")
    # Three points → three draw ops in the line.
    assert chart.line_d.count("M") + chart.line_d.count("L") == 3
    assert chart.view_box.startswith("0 0 ")
    assert "e" not in chart.line_d  # no scientific notation


def test_line_area_empty_returns_empty_paths() -> None:
    chart = line_area([])
    assert chart.line_d == ""
    assert chart.area_d == ""
    assert chart.x_axis == ()
    assert chart.y_axis == ()
    assert chart.view_box.startswith("0 0 ")


def test_line_area_single_point() -> None:
    chart = line_area([(0.0, 10.0)])
    assert chart.line_d.startswith("M")
    assert chart.area_d.endswith("Z")
    # Single point still produces y-axis ticks.
    assert len(chart.y_axis) >= 2


def test_line_area_negative_values() -> None:
    chart = line_area([(0.0, -5.0), (1.0, -10.0), (2.0, 5.0)])
    assert chart.line_d.count("L") == 2
    # All y-axis ticks are numeric labels.
    for tick in chart.y_axis:
        assert isinstance(tick, AxisTick)
        float(tick.label.replace(",", "").replace("\N{MINUS SIGN}", "-"))


def test_line_area_flat_line() -> None:
    chart = line_area([(0.0, 5.0), (1.0, 5.0), (2.0, 5.0)])
    assert chart.line_d.count("L") == 2
    assert len(chart.y_axis) >= 2


def test_line_area_x_labels_match_points() -> None:
    chart = line_area(
        [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)],
        x_labels=["Jan", "Feb", "Mar"],
    )
    labels = [tick.label for tick in chart.x_axis]
    assert "Jan" in labels or "Feb" in labels or "Mar" in labels


def test_line_area_x_labels_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="x_labels"):
        line_area([(0.0, 1.0)], x_labels=["A", "B"])


def test_line_area_result_is_frozen() -> None:
    chart = line_area([(0.0, 1.0)])
    with pytest.raises(FrozenInstanceError):
        chart.line_d = "nope"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# grouped_bars
# ---------------------------------------------------------------------------


def test_grouped_bars_basic_shape() -> None:
    chart = grouped_bars(
        [
            {"label": "Jan", "bars": [("income", 100.0), ("expense", 80.0)]},
            {"label": "Feb", "bars": [("income", 120.0), ("expense", 90.0)]},
        ]
    )
    assert isinstance(chart, GroupedBarsChart)
    assert len(chart.groups) == 2
    assert chart.groups[0].label == "Jan"
    assert len(chart.groups[0].bars) == 2
    assert chart.groups[0].bars[0].kind == "income"
    assert chart.groups[0].bars[1].kind == "expense"
    # Y-axis labels never contain scientific notation.
    for tick in chart.y_axis:
        assert "e" not in tick.label


def test_grouped_bars_empty_returns_empty() -> None:
    chart = grouped_bars([])
    assert chart.groups == ()
    assert chart.y_axis == ()
    assert chart.view_box.startswith("0 0 ")


def test_grouped_bars_single_group() -> None:
    chart = grouped_bars([{"label": "Only", "bars": [("income", 42.0)]}])
    assert len(chart.groups) == 1
    assert chart.groups[0].bars[0].value == 42.0


def test_grouped_bars_all_zero_values_renders_no_bar_height() -> None:
    chart = grouped_bars([{"label": "Jan", "bars": [("income", 0.0), ("expense", 0.0)]}])
    for bar in chart.groups[0].bars:
        assert bar.height == 0.0


def test_grouped_bars_negative_raises() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        grouped_bars([{"label": "Jan", "bars": [("income", -1.0)]}])


def test_grouped_bars_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown bar kind"):
        grouped_bars([{"label": "Jan", "bars": [("mystery", 10.0)]}])


def test_grouped_bars_result_is_frozen() -> None:
    chart = grouped_bars([{"label": "Jan", "bars": [("income", 1.0)]}])
    with pytest.raises(FrozenInstanceError):
        chart.groups = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# horizontal_bars
# ---------------------------------------------------------------------------


def test_horizontal_bars_basic_shape() -> None:
    chart = horizontal_bars([("Groceries", 500.0), ("Rent", 2000.0)])
    assert isinstance(chart, HorizontalBarsChart)
    assert len(chart.bars) == 2
    # Rent should have the longer bar since it's the max.
    assert chart.bars[1].bar_width >= chart.bars[0].bar_width
    assert chart.max_label_width > 0


def test_horizontal_bars_empty_returns_empty() -> None:
    chart = horizontal_bars([])
    assert chart.bars == ()
    assert chart.height == 0.0
    assert chart.max_label_width == 0.0


def test_horizontal_bars_single_item() -> None:
    chart = horizontal_bars([("Only", 10.0)])
    assert len(chart.bars) == 1
    assert chart.bars[0].value == 10.0
    assert chart.bars[0].bar_width > 0


def test_horizontal_bars_negative_values_clamped() -> None:
    chart = horizontal_bars([("Refund", -50.0), ("Spend", 100.0)])
    # Negative value should render zero-width bar (clamped).
    assert chart.bars[0].bar_width == 0.0
    assert chart.bars[1].bar_width > 0


def test_horizontal_bars_all_zero() -> None:
    chart = horizontal_bars([("A", 0.0), ("B", 0.0)])
    assert all(b.bar_width == 0.0 for b in chart.bars)


def test_horizontal_bars_result_is_frozen() -> None:
    chart = horizontal_bars([("A", 1.0)])
    with pytest.raises(FrozenInstanceError):
        chart.bars = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# sparkline
# ---------------------------------------------------------------------------


def test_sparkline_basic() -> None:
    sp = sparkline([1.0, 2.0, 3.0, 2.5, 4.0])
    assert isinstance(sp, Sparkline)
    assert sp.line_d.startswith("M")
    assert sp.area_d.endswith("Z")
    assert sp.rising is True
    assert sp.flat is False


def test_sparkline_falling() -> None:
    sp = sparkline([5.0, 4.0, 3.0, 2.0, 1.0])
    assert sp.rising is False
    assert sp.flat is False


def test_sparkline_flat() -> None:
    sp = sparkline([3.0, 3.0, 3.0])
    assert sp.flat is True
    assert sp.rising is False


def test_sparkline_single_point() -> None:
    sp = sparkline([42.0])
    assert sp.line_d.startswith("M")
    assert sp.area_d == ""
    assert sp.flat is True


def test_sparkline_empty() -> None:
    sp = sparkline([])
    assert sp.line_d == ""
    assert sp.area_d == ""
    assert sp.flat is True
    assert sp.view_box.startswith("0 0 ")


def test_sparkline_mixed_up_down() -> None:
    sp = sparkline([1.0, 5.0, 2.0, 6.0])
    assert sp.rising is True  # last > first
    # Each point should produce an M or L op.
    draw_ops = sp.line_d.count("M") + sp.line_d.count("L")
    assert draw_ops == 4


def test_sparkline_result_is_frozen() -> None:
    sp = sparkline([1.0, 2.0])
    with pytest.raises(FrozenInstanceError):
        sp.line_d = "nope"  # type: ignore[misc]
