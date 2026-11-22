"""Pure SVG chart geometry helpers (T-R47, ADR-0054).

Replace Plotly with a tiny module that computes SVG geometry server-side.
Templates consume the frozen dataclasses and render inline ``<svg>``. All
math is deterministic and depends only on the inputs — no I/O, no DB.

Three main shapes cover v2:

* ``line_area(points)`` — projected balance line + soft area fill.
* ``grouped_bars(groups)`` — income vs expense monthly bars.
* ``horizontal_bars(items)`` — spend-by-category list.

Plus a narrow-aspect ``sparkline(points)`` for the Accounts trend column
(T-R68). All numeric outputs are formatted with three decimal places so the
browser renders consistently (no scientific notation).

Pure. No side effects. Immutable. Mutation attempts on returned dataclasses
raise ``FrozenInstanceError``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from budget_planner.domain.enums import Direction
from budget_planner.domain.money import format_axis_number, major_float
from budget_planner.services.analytics import AnalyticsBundle

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

_NUM_FMT = "{:.3f}"
_NICE_FRACTIONS: tuple[float, ...] = (1.0, 2.0, 2.5, 5.0, 10.0)
_DEFAULT_TARGET_TICKS = 5


def _fmt(value: float) -> str:
    """Format ``value`` for SVG attribute output.

    Fixed 3-decimal precision avoids scientific notation on very small or
    very large numbers and keeps path strings stable across runs.
    """
    return _NUM_FMT.format(value)


def _nice_axis(
    data_min: float,
    data_max: float,
    target_ticks: int = _DEFAULT_TARGET_TICKS,
) -> tuple[float, float, float]:
    """Return ``(min, max, step)`` using the 1-2-5 nice-number heuristic.

    Classic axis-labeling algorithm: pick the step as a round
    ``1 · 2 · 2.5 · 5 * 10^k``, then expand ``[min, max]`` outward to the
    nearest multiple so axis labels land on clean numbers.

    Degenerate inputs collapse gracefully: identical ``min`` and ``max``
    produce a unit range centred on the value; non-positive tick counts
    fall back to the default.
    """
    if target_ticks < 1:
        target_ticks = _DEFAULT_TARGET_TICKS
    if data_min == data_max:
        delta = max(abs(data_min), 1.0)
        data_min -= delta * 0.5
        data_max += delta * 0.5
    span = data_max - data_min
    rough_step = span / target_ticks
    exponent = math.floor(math.log10(rough_step)) if rough_step > 0 else 0
    base = math.pow(10.0, exponent)
    normalized = rough_step / base
    nice_fraction = next(f for f in _NICE_FRACTIONS if normalized <= f)
    step = nice_fraction * base
    nice_min = math.floor(data_min / step) * step
    nice_max = math.ceil(data_max / step) * step
    return (nice_min, nice_max, step)


def _axis_ticks(nice_min: float, nice_max: float, step: float) -> tuple[float, ...]:
    """Return the tick positions covering ``[nice_min, nice_max]`` inclusive."""
    if step <= 0:
        return (nice_min,)
    ticks: list[float] = []
    # Floating-point creep — add half a step tolerance to the stop condition.
    current = nice_min
    while current <= nice_max + step * 0.5:
        ticks.append(round(current, 10))
        current += step
    return tuple(ticks)


# ---------------------------------------------------------------------------
# Line + area chart (Plan · Forecast)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AxisTick:
    """One axis tick (position in SVG coords + display label)."""

    position: float
    label: str


@dataclass(frozen=True, slots=True)
class LinePoint:
    """One rendered line-chart marker position (SVG coords)."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class LineAreaChart:
    """SVG geometry for a line + area chart with simple axes."""

    line_d: str
    area_d: str
    x_axis: tuple[AxisTick, ...]
    y_axis: tuple[AxisTick, ...]
    view_box: str
    width: float
    height: float
    points: tuple[LinePoint, ...] = ()

    @property
    def plot_right(self) -> float:
        """Right edge of the plot area (gridline end)."""
        return self.width - _LINE_AREA_PAD_RIGHT

    @property
    def x_label_y(self) -> float:
        """Baseline of the x-axis labels."""
        return self.height - _X_LABEL_INSET


_X_LABEL_INSET = 10.0
_LINE_AREA_WIDTH = 600.0
_LINE_AREA_HEIGHT = 240.0
_LINE_AREA_PAD_LEFT = 48.0
_LINE_AREA_PAD_RIGHT = 16.0
_LINE_AREA_PAD_TOP = 16.0
_LINE_AREA_PAD_BOTTOM = 32.0


@dataclass(frozen=True, slots=True)
class _Plot:
    """Inner plot box plus the nice y-axis scale shared by the chart builders."""

    left: float
    bottom: float
    width: float
    height: float
    y_min: float
    y_max: float
    y_step: float

    @property
    def y_span(self) -> float:
        """Axis range (never zero)."""
        return self.y_max - self.y_min or 1.0

    def bar_height(self, value: float) -> float:
        """Pixel height of ``value`` above the axis minimum."""
        return ((value - self.y_min) / self.y_span) * self.height

    def y(self, value: float) -> float:
        """SVG y coordinate of ``value``."""
        return self.bottom - self.bar_height(value)

    def y_ticks(self) -> tuple[AxisTick, ...]:
        """Y-axis ticks from the nice step."""
        return tuple(
            AxisTick(position=self.y(value), label=format_axis_number(value))
            for value in _axis_ticks(self.y_min, self.y_max, self.y_step)
        )


def line_area(
    points: Sequence[tuple[float, float]],
    *,
    width: float = _LINE_AREA_WIDTH,
    height: float = _LINE_AREA_HEIGHT,
    x_labels: Sequence[str] | None = None,
) -> LineAreaChart:
    """Compute SVG geometry for a line + area chart.

    ``points`` are ``(x, y)`` data-space tuples (empty input gives an empty chart
    with a valid view-box); ``x_labels`` optionally replaces numeric x-axis labels
    and must match ``points`` in length.
    """
    view_box = f"0 0 {_fmt(width)} {_fmt(height)}"
    if not points:
        return LineAreaChart(
            line_d="",
            area_d="",
            x_axis=(),
            y_axis=(),
            view_box=view_box,
            width=width,
            height=height,
        )

    nice_min, nice_max, y_step = _nice_axis(min(p[1] for p in points), max(p[1] for p in points))
    plot = _Plot(
        left=_LINE_AREA_PAD_LEFT,
        bottom=height - _LINE_AREA_PAD_BOTTOM,
        width=(width - _LINE_AREA_PAD_RIGHT) - _LINE_AREA_PAD_LEFT,
        height=(height - _LINE_AREA_PAD_BOTTOM) - _LINE_AREA_PAD_TOP,
        y_min=nice_min,
        y_max=nice_max,
        y_step=y_step,
    )
    rendered = _line_points(points, plot)
    line_d, area_d = _line_area_paths(rendered, plot)
    return LineAreaChart(
        line_d=line_d,
        area_d=area_d,
        x_axis=_line_x_ticks(rendered, x_labels),
        y_axis=plot.y_ticks(),
        view_box=view_box,
        width=width,
        height=height,
        points=tuple(rendered),
    )


def _line_points(points: Sequence[tuple[float, float]], plot: _Plot) -> list[LinePoint]:
    """Map data points to SVG coordinates (a single point sits mid-box)."""
    if len(points) == 1:
        return [LinePoint(x=plot.left + plot.width * 0.5, y=plot.y(points[0][1]))]
    xs = [p[0] for p in points]
    x_min = min(xs)
    x_span = (max(xs) - x_min) or 1.0
    return [
        LinePoint(x=plot.left + ((dx - x_min) / x_span) * plot.width, y=plot.y(dy))
        for dx, dy in points
    ]


def _line_area_paths(rendered: Sequence[LinePoint], plot: _Plot) -> tuple[str, str]:
    """SVG ``d`` strings for the line and its closed area."""
    if len(rendered) == 1:
        only = rendered[0]
        head = f"M{_fmt(only.x)} {_fmt(only.y)}"
        return head, f"{head} L{_fmt(only.x)} {_fmt(plot.bottom)} Z"
    segments = [
        f"{'M' if i == 0 else 'L'}{_fmt(pt.x)} {_fmt(pt.y)}" for i, pt in enumerate(rendered)
    ]
    area = [
        *segments,
        f"L{_fmt(rendered[-1].x)} {_fmt(plot.bottom)}",
        f"L{_fmt(plot.left)} {_fmt(plot.bottom)} Z",
    ]
    return " ".join(segments), " ".join(area)


def _line_x_ticks(
    rendered: Sequence[LinePoint], x_labels: Sequence[str] | None
) -> tuple[AxisTick, ...]:
    """X-axis ticks: explicit labels only, skipping every nth to stay legible."""
    if x_labels is None:
        return ()
    if len(x_labels) != len(rendered):
        raise ValueError(
            f"x_labels length {len(x_labels)} must match points length {len(rendered)}"
        )
    step = max(1, len(rendered) // 6)
    return tuple(
        AxisTick(position=rendered[i].x, label=label)
        for i, label in enumerate(x_labels)
        if i % step == 0 or i == len(rendered) - 1
    )


# ---------------------------------------------------------------------------
# Grouped bars (Plan · Analytics — income vs expense)
# ---------------------------------------------------------------------------

BarKind = Literal["income", "expense"]


@dataclass(frozen=True, slots=True)
class Bar:
    """One rendered bar (position + value + series kind)."""

    kind: BarKind
    x: float
    y: float
    width: float
    height: float
    value: float


@dataclass(frozen=True, slots=True)
class GroupedBarGroup:
    """One group of bars rendered under a single label."""

    label: str
    center_x: float
    bars: tuple[Bar, ...]


@dataclass(frozen=True, slots=True)
class GroupedBarsChart:
    """SVG geometry for a grouped-bar chart."""

    groups: tuple[GroupedBarGroup, ...]
    y_axis: tuple[AxisTick, ...]
    view_box: str
    width: float
    height: float

    @property
    def plot_right(self) -> float:
        """Right edge of the plot area (gridline end)."""
        return self.width - _GROUPED_PAD_RIGHT

    @property
    def x_label_y(self) -> float:
        """Baseline of the x-axis labels."""
        return self.height - _X_LABEL_INSET


_GROUPED_WIDTH = 600.0
_GROUPED_HEIGHT = 240.0
_GROUPED_PAD_LEFT = 48.0
_GROUPED_PAD_RIGHT = 16.0
_GROUPED_PAD_TOP = 16.0
_GROUPED_PAD_BOTTOM = 48.0
_GROUPED_INNER_GAP = 2.0  # between bars inside a group
_GROUPED_GROUP_GAP_RATIO = 0.3  # fraction of group slot used as padding


def grouped_bars(
    groups: Sequence[dict[str, Any]],
    *,
    width: float = _GROUPED_WIDTH,
    height: float = _GROUPED_HEIGHT,
) -> GroupedBarsChart:
    """Compute geometry for grouped bars.

    Each group is a mapping ``{"label": str, "bars": [(kind, value), ...]}``.
    All ``value`` entries must be non-negative; negatives raise.
    """
    view_box = f"0 0 {_fmt(width)} {_fmt(height)}"
    if not groups:
        return GroupedBarsChart(
            groups=(),
            y_axis=(),
            view_box=view_box,
            width=width,
            height=height,
        )

    normalized = _normalize_groups(groups)
    max_value = max((val for _, bars in normalized for _, val in bars), default=0.0)
    nice_min, nice_max, y_step = _grouped_axis(max_value)
    inner_left = _GROUPED_PAD_LEFT
    plot = _Plot(
        left=inner_left,
        bottom=height - _GROUPED_PAD_BOTTOM,
        width=(width - _GROUPED_PAD_RIGHT) - inner_left,
        height=(height - _GROUPED_PAD_BOTTOM) - _GROUPED_PAD_TOP,
        y_min=nice_min,
        y_max=nice_max,
        y_step=y_step,
    )
    group_slot = plot.width / len(normalized)
    return GroupedBarsChart(
        groups=tuple(
            _bar_group(label, bars, plot, g_idx, group_slot)
            for g_idx, (label, bars) in enumerate(normalized)
        ),
        y_axis=plot.y_ticks(),
        view_box=view_box,
        width=width,
        height=height,
    )


_NormalizedGroup = tuple[str, tuple[tuple[BarKind, float], ...]]


def _normalize_groups(groups: Sequence[Mapping[str, object]]) -> list[_NormalizedGroup]:
    """Validate the raw group mappings into ``(label, ((kind, value), ...))`` tuples."""
    normalized: list[_NormalizedGroup] = []
    for raw in groups:
        label = str(raw.get("label", ""))
        raw_bars = cast(Iterable[tuple[str, float]], raw.get("bars", ()))
        bar_entries: list[tuple[BarKind, float]] = []
        for kind, value in raw_bars:
            if kind not in ("income", "expense"):
                raise ValueError(f"unknown bar kind: {kind!r}")
            if value < 0:
                raise ValueError("grouped_bars values must be >= 0")
            bar_entries.append((cast(BarKind, kind), float(value)))
        normalized.append((label, tuple(bar_entries)))
    return normalized


def _grouped_axis(max_value: float) -> tuple[float, float, float]:
    """Nice (min, max, step) for the grouped-bars axis; min is pinned to zero."""
    if max_value <= 0:
        return 0.0, 1.0, 1.0
    nice_min, nice_max, y_step = _nice_axis(0.0, max_value)
    return min(nice_min, 0.0), nice_max, y_step


def _bar_group(
    label: str,
    bars: Sequence[tuple[BarKind, float]],
    plot: _Plot,
    g_idx: int,
    group_slot: float,
) -> GroupedBarGroup:
    """Geometry of one labelled group of bars inside its slot."""
    group_padding = group_slot * _GROUPED_GROUP_GAP_RATIO * 0.5
    bar_area = group_slot - 2 * group_padding
    slot_start = plot.left + g_idx * group_slot
    bar_count = len(bars) or 1
    total_gap = _GROUPED_INNER_GAP * (bar_count - 1)
    bar_width = max((bar_area - total_gap) / bar_count, 1.0)
    rendered = tuple(
        _bar(
            kind,
            value,
            plot,
            x=slot_start + group_padding + b_idx * (bar_width + _GROUPED_INNER_GAP),
            width=bar_width,
        )
        for b_idx, (kind, value) in enumerate(bars)
    )
    return GroupedBarGroup(label=label, center_x=slot_start + group_slot * 0.5, bars=rendered)


def _bar(kind: BarKind, value: float, plot: _Plot, *, x: float, width: float) -> Bar:
    """One bar rising from the plot baseline (zero values get zero height)."""
    bar_height = plot.bar_height(value) if value > 0 else 0.0
    return Bar(
        kind=kind, x=x, y=plot.bottom - bar_height, width=width, height=bar_height, value=value
    )


# ---------------------------------------------------------------------------
# Horizontal bars (Plan · Analytics — spend by category)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HorizontalBar:
    """One horizontal bar (label + bar geometry + raw value)."""

    label: str
    value: float
    y: float
    bar_x: float
    bar_width: float
    bar_height: float
    value_label: str


@dataclass(frozen=True, slots=True)
class HorizontalBarsChart:
    """SVG geometry for a horizontal-bars list."""

    bars: tuple[HorizontalBar, ...]
    max_label_width: float
    view_box: str
    width: float
    height: float


_HORIZONTAL_WIDTH = 600.0
_HORIZONTAL_ROW_HEIGHT = 32.0
_HORIZONTAL_BAR_HEIGHT = 18.0
_HORIZONTAL_LABEL_RATIO = 0.3  # fraction of width reserved for category label
_HORIZONTAL_VALUE_RATIO = 0.18  # fraction reserved on the right for value text
_HORIZONTAL_LABEL_CHAR_WIDTH = 7.2  # rough px per char for label-column sizing


def horizontal_bars(
    items: Sequence[tuple[str, float]],
    *,
    width: float = _HORIZONTAL_WIDTH,
    row_height: float = _HORIZONTAL_ROW_HEIGHT,
) -> HorizontalBarsChart:
    """Compute geometry for a horizontal-bar list.

    Each item is ``(label, value)``. Negative values are allowed and
    rendered as zero-width bars (geometry only — the template may style
    them differently). The first row sits at the top; rows stack
    downwards. The chart height is derived from the row count.
    """
    if not items:
        return HorizontalBarsChart(
            bars=(),
            max_label_width=0.0,
            view_box=f"0 0 {_fmt(width)} 0",
            width=width,
            height=0.0,
        )

    height = row_height * len(items)
    max_value = max((v for _, v in items), default=0.0)
    label_col = width * _HORIZONTAL_LABEL_RATIO
    bar_track = max(width - label_col - width * _HORIZONTAL_VALUE_RATIO, 1.0)
    rendered = tuple(
        _horizontal_row(
            i,
            label,
            value,
            row_height=row_height,
            bar_x=label_col,
            bar_track=bar_track,
            max_value=max_value,
        )
        for i, (label, value) in enumerate(items)
    )
    return HorizontalBarsChart(
        bars=rendered,
        max_label_width=max(len(label) * _HORIZONTAL_LABEL_CHAR_WIDTH for label, _ in items),
        view_box=f"0 0 {_fmt(width)} {_fmt(height)}",
        width=width,
        height=height,
    )


def _horizontal_row(
    index: int,
    label: str,
    value: float,
    *,
    row_height: float,
    bar_x: float,
    bar_track: float,
    max_value: float,
) -> HorizontalBar:
    """Geometry of one row; negatives clamp to a zero-width bar."""
    clamped = max(value, 0.0)
    bar_width = (clamped / max_value) * bar_track if max_value > 0 else 0.0
    bar_y_offset = (row_height - _HORIZONTAL_BAR_HEIGHT) * 0.5
    return HorizontalBar(
        label=label,
        value=value,
        y=index * row_height + bar_y_offset,
        bar_x=bar_x,
        bar_width=bar_width,
        bar_height=_HORIZONTAL_BAR_HEIGHT,
        value_label=format_axis_number(value),
    )


# ---------------------------------------------------------------------------
# Sparkline (Accounts trend column, T-R68)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Sparkline:
    """SVG geometry for an inline sparkline (no axes)."""

    line_d: str
    area_d: str
    view_box: str
    width: float
    height: float
    rising: bool
    flat: bool


def sparkline(
    points: Sequence[float],
    *,
    width: float = 80.0,
    height: float = 20.0,
) -> Sparkline:
    """Compute geometry for a narrow sparkline.

    Normalises ``points`` into the ``width x height`` box with a 1 px
    margin so the stroke never clips. ``rising`` is derived from the
    first vs last point (``False`` when flat or falling); ``flat``
    indicates equal min/max. Empty input returns an empty path with a
    valid view-box.
    """
    view_box = f"0 0 {_fmt(width)} {_fmt(height)}"
    if not points:
        return Sparkline(
            line_d="",
            area_d="",
            view_box=view_box,
            width=width,
            height=height,
            rising=False,
            flat=True,
        )

    if len(points) == 1:
        center_y = height * 0.5
        center_x = width * 0.5
        return Sparkline(
            line_d=f"M{_fmt(center_x)} {_fmt(center_y)}",
            area_d="",
            view_box=view_box,
            width=width,
            height=height,
            rising=False,
            flat=True,
        )

    line_d, area_d = _sparkline_paths(points, width, height)
    return Sparkline(
        line_d=line_d,
        area_d=area_d,
        view_box=view_box,
        width=width,
        height=height,
        rising=points[-1] > points[0],
        flat=max(points) == min(points),
    )


_SPARKLINE_MARGIN = 1.0


def _sparkline_paths(points: Sequence[float], width: float, height: float) -> tuple[str, str]:
    """Line and area ``d`` strings normalised into the box with a 1 px margin."""
    y_min = min(points)
    y_span = (max(points) - y_min) or 1.0
    step_x = width / (len(points) - 1)
    inner_height = height - 2 * _SPARKLINE_MARGIN
    segments = [
        f"{'M' if i == 0 else 'L'}{_fmt(i * step_x)} "
        f"{_fmt(height - _SPARKLINE_MARGIN - ((value - y_min) / y_span) * inner_height)}"
        for i, value in enumerate(points)
    ]
    area = [*segments, f"L{_fmt(width)} {_fmt(height)}", f"L0 {_fmt(height)} Z"]
    return " ".join(segments), " ".join(area)


__all__ = [
    "AxisTick",
    "Bar",
    "GroupedBarGroup",
    "GroupedBarsChart",
    "HorizontalBar",
    "HorizontalBarsChart",
    "LineAreaChart",
    "Sparkline",
    "grouped_bars",
    "horizontal_bars",
    "line_area",
    "sparkline",
]


def line_area_minor(
    values_minor: Sequence[int], currency: str, labels: Sequence[str]
) -> LineAreaChart:
    """Line-area chart of minor-unit balances, scaled by the currency exponent."""
    points = tuple((float(i), major_float(v, currency)) for i, v in enumerate(values_minor))
    return line_area(points, x_labels=labels)


def analytics_charts(
    bundle: AnalyticsBundle, currency: str
) -> tuple[HorizontalBarsChart, GroupedBarsChart]:
    """Spend-by-category bars and income/expense grouped bars for the Analytics tab."""
    spend_items = tuple(
        (row.category_name, major_float(row.amount_minor, currency))
        for row in bundle.spend_by_category
    )
    flow_groups = tuple(
        {
            "label": point.label[-5:],  # YYYY-MM -> MM-?; keep tail for density
            "bars": [
                (Direction.INCOME.value, major_float(point.income_minor, currency)),
                (Direction.EXPENSE.value, major_float(point.expense_minor, currency)),
            ],
        }
        for point in bundle.income_vs_expense_monthly
    )
    return horizontal_bars(spend_items), grouped_bars(flow_groups)
