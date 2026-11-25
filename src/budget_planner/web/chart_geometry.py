"""Server-built SVG geometry of the Rising Dough charts (T-UR12, ADR-0107 section 5, ADR-0123).

Follows the handoff's ``charts/forecast.html`` and ``charts/income-vs-expense.html`` notes
(ADR-0147 section 4: the visual overlay generates its geometry rows from these same functions).
Every coordinate is a ready-to-print string (``charts.svg_number``, three decimals), so
templates only print. Pure: no I/O, no clock; amounts come in as minor units and are scaled by
the currency exponent through ``domain.money``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from budget_planner.domain.money import format_axis_number, format_figure, major_float
from budget_planner.services.analytics import MonthlyFlow
from budget_planner.services.forecast import MonthlyProjectionPoint
from budget_planner.web.charts import nice_scale, svg_number as fmt

_EN_DASH = "\N{EN DASH}"
_DOT = "\N{MIDDLE DOT}"
_TIP_PAD = 14.0
_TIP_LINE = 18.0
_TICK_LABEL_DROP = 4.0
_THOUSAND = 1000.0


def _px(value: float) -> str:
    """Whole-pixel measure (``190``)."""
    return str(int(value))


def _month_abbr(month: date) -> str:
    """Upper-case three-letter month (``OCT``)."""
    return month.strftime("%b").upper()


def _month_label(month: date) -> str:
    """``Oct 2026``."""
    return month.strftime("%b %Y")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


@dataclass(frozen=True, slots=True)
class Scale:
    """Linear y scale of a plot: ``y(low)`` is the bottom edge, ``y(high)`` the top edge."""

    low: float
    high: float
    top: float
    bottom: float

    def y(self, value: float) -> float:
        """SVG y coordinate of ``value`` (a flat range maps to the bottom edge)."""
        span = self.high - self.low or 1.0
        return self.bottom - (value - self.low) / span * (self.bottom - self.top)


@dataclass(frozen=True, slots=True)
class Tooltip:
    """Tooltip box and its three text lines (SVG coordinates)."""

    x: str
    y: str
    width: str
    height: str
    text_x: str
    line_y: tuple[str, str, str]
    title: str
    value: str
    detail: str


def _tooltip(
    left: float, top: float, size: tuple[float, float], lines: tuple[str, str, str]
) -> Tooltip:
    """Tooltip box at ``(left, top)`` of ``size`` with its caption, value and detail lines."""
    return Tooltip(
        x=fmt(left),
        y=fmt(top),
        width=_px(size[0]),
        height=_px(size[1]),
        text_x=fmt(left + _TIP_PAD),
        line_y=(fmt(top + _TIP_LINE), fmt(top + 2 * _TIP_LINE), fmt(top + 3 * _TIP_LINE)),
        title=lines[0],
        value=lines[1],
        detail=lines[2],
    )


@dataclass(frozen=True, slots=True)
class GridLine:
    """Horizontal gridline with its y-axis label."""

    y: str
    label_y: str
    label: str


def _grid(
    scale: Scale, ticks: Sequence[float], label_of: Callable[[float], str]
) -> tuple[GridLine, ...]:
    """Gridlines at ``ticks``; ``label_of`` formats a tick value."""
    return tuple(
        GridLine(y=fmt(scale.y(t)), label_y=fmt(scale.y(t) + _TICK_LABEL_DROP), label=label_of(t))
        for t in ticks
    )


# --- forecast ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthTick:
    """X-axis tick under a month; ``month`` and ``year`` are empty when the label is thinned out."""

    x: str
    month: str
    year: str


@dataclass(frozen=True, slots=True)
class ForecastDot:
    """One month of the forecast line: dot, hover guide, tooltip and accessible label."""

    x: str
    y: str
    aria_label: str
    tooltip: Tooltip


@dataclass(frozen=True, slots=True)
class ForecastChart:
    """Server-built geometry of ``charts/forecast`` (viewBox 1184 x 330)."""

    view_box: str
    aria_label: str
    caption: str
    plot_left: str
    plot_right: str
    plot_top: str
    plot_bottom: str
    grid: tuple[GridLine, ...]
    ticks: tuple[MonthTick, ...]
    area_points: str
    line_points: str
    dots: tuple[ForecastDot, ...]


_FC_WIDTH = 1184
_FC_HEIGHT = 330
_FC_LEFT = 64.0
_FC_RIGHT = 1158.0
_FC_TOP = 16.0
_FC_BOTTOM = 262.0
_FC_INSET = 8.0
_FC_TIP_SIZE = (190.0, 64.0)
_FC_TIP_GAP = 14.0
_FC_MIN_LABEL_SPACING = 40.0


def _label_every(spacing: float) -> int:
    """Label every n-th month so neighbouring labels keep ``_FC_MIN_LABEL_SPACING`` px apart."""
    every = 1
    while spacing * every < _FC_MIN_LABEL_SPACING:
        every += 1
    return every


def _forecast_tooltip(month: date, balance: str, net: str, x: float, y: float) -> Tooltip:
    width, height = _FC_TIP_SIZE
    top = y - height - _FC_TIP_GAP
    if top < 0:  # would clip the top: flip below the point
        top = y + _FC_TIP_GAP
    lines = (
        f"{_month_abbr(month)} {month.year} {_DOT} END OF MONTH",
        balance,
        f"net {net}",
    )
    return _tooltip(_clamp(x - width / 2, 0.0, _FC_WIDTH - width), top, _FC_TIP_SIZE, lines)


def _forecast_xs(count: int) -> tuple[tuple[float, ...], float]:
    """X of every month (even spread, 8 px inset) and the spacing between neighbours."""
    plot_w = _FC_RIGHT - _FC_LEFT
    if count == 1:
        return (_FC_LEFT + plot_w / 2,), plot_w
    spacing = (plot_w - 2 * _FC_INSET) / (count - 1)
    return tuple(_FC_LEFT + _FC_INSET + i * spacing for i in range(count)), spacing


def _forecast_dots(
    points: Sequence[MonthlyProjectionPoint],
    xs: Sequence[float],
    ys: Sequence[float],
    currency: str,
) -> tuple[ForecastDot, ...]:
    dots: list[ForecastDot] = []
    for p, x, y in zip(points, xs, ys, strict=True):
        balance = f"{format_figure(p.end_balance_minor, currency)} {currency}"
        net = format_figure(p.net_minor, currency, plus=True)
        dots.append(
            ForecastDot(
                x=fmt(x),
                y=fmt(y),
                aria_label=f"{_month_label(p.month)}: {balance}, net {net}",
                tooltip=_forecast_tooltip(p.month, balance, net, x, y),
            )
        )
    return tuple(dots)


def _forecast(
    aria_label: str,
    caption: str,
    *,
    grid: tuple[GridLine, ...] = (),
    ticks: tuple[MonthTick, ...] = (),
    area_and_line: tuple[str, str] = ("", ""),
    dots: tuple[ForecastDot, ...] = (),
) -> ForecastChart:
    """A chart with the fixed plot frame around the variable parts."""
    return ForecastChart(
        view_box=f"0 0 {_FC_WIDTH} {_FC_HEIGHT}",
        aria_label=aria_label,
        caption=caption,
        plot_left=_px(_FC_LEFT),
        plot_right=_px(_FC_RIGHT),
        plot_top=fmt(_FC_TOP),
        plot_bottom=fmt(_FC_BOTTOM),
        grid=grid,
        ticks=ticks,
        area_points=area_and_line[0],
        line_points=area_and_line[1],
        dots=dots,
    )


def forecast_chart(
    points: Sequence[MonthlyProjectionPoint], currency: str, *, caption_prefix: str
) -> ForecastChart:
    """Geometry of the projected-balance chart: line, area, one dot and tooltip per month.

    The y axis is the 1-2-5 nice scale of the balances; points are spread evenly with an
    8 px inset on both sides (98 px apart for 12 months). Month labels are thinned out when
    they would be closer than 40 px.
    """
    if not points:
        return _forecast(
            "Projected balance by month: no data.", f"{caption_prefix} {_DOT} {currency}"
        )
    values = tuple(major_float(p.end_balance_minor, currency) for p in points)
    low, high, tick_values = nice_scale(min(values), max(values))
    scale = Scale(low, high, _FC_TOP, _FC_BOTTOM)
    xs, spacing = _forecast_xs(len(points))
    ys = tuple(scale.y(v) for v in values)
    every = _label_every(spacing)
    line = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in zip(xs, ys, strict=True))
    base = _px(_FC_BOTTOM)
    first, last = points[0].month, points[-1].month
    return _forecast(
        aria_label=(
            f"Projected balance by month, {_month_label(first)} to {_month_label(last)}. "
            "Each month has a point; hover or focus a point for its end-of-month balance."
        ),
        caption=(
            f"{caption_prefix} {_DOT} {_month_abbr(first)} {first.year} {_EN_DASH} "
            f"{_month_abbr(last)} {last.year} {_DOT} {currency}"
        ),
        grid=_grid(scale, tick_values, format_axis_number),
        ticks=tuple(
            MonthTick(
                x=fmt(x),
                month=_month_abbr(p.month) if i % every == 0 else "",
                year=str(p.month.year) if i % every == 0 else "",
            )
            for i, (x, p) in enumerate(zip(xs, points, strict=True))
        ),
        area_and_line=(f"{fmt(xs[0])},{base} {line} {fmt(xs[-1])},{base}", line),
        dots=_forecast_dots(points, xs, ys, currency),
    )


# --- income vs expense -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Loaf:
    """One income or expense loaf: its path (empty for a zero amount) and modifier flags."""

    d: str
    is_expense: bool
    is_now: bool


@dataclass(frozen=True, slots=True)
class FlowMonth:
    """One month of the income-versus-expense chart (band, two loaves, labels, tooltip)."""

    aria_label: str
    band_x: str
    band_width: str
    loaves: tuple[Loaf, ...]
    label_x: str
    month: str
    year: str
    tooltip: Tooltip


@dataclass(frozen=True, slots=True)
class FlowChart:
    """Server-built geometry of ``charts/income-vs-expense`` (viewBox 520 x 300)."""

    view_box: str
    aria_label: str
    plot_left: str
    plot_right: str
    plot_bottom: str
    grid: tuple[GridLine, ...]
    months: tuple[FlowMonth, ...]


_FL_WIDTH = 520
_FL_HEIGHT = 300
_FL_LEFT = 50.0
_FL_TOP = 16.0
_FL_BOTTOM = 250.0
_FL_SLOT = 116.0
_FL_BAND_OFFSET = 10.0
_FL_BAND_W = 108.0
_FL_INCOME_OFFSET = 16.0
_FL_EXPENSE_OFFSET = 58.0
_FL_LOAF_W = 34.0
_FL_CORNER = 4.0
_FL_LABEL_OFFSET = 54.0
_FL_TIP_SIZE = (270.0, 64.0)
_FL_TIP_GAP = 14.0


def _loaf_path(x: float, width: float, apex: float) -> str:
    """Loaf outline: 4 px base corners, flat sides, a half-circle top starting at ``apex``."""
    bottom, right, radius, corner = _FL_BOTTOM, x + width, width / 2, _FL_CORNER
    return (
        f"M{fmt(x)},{fmt(bottom - corner)} Q{fmt(x)},{fmt(bottom)} "
        f"{fmt(x + corner)},{fmt(bottom)} L{fmt(right - corner)},{fmt(bottom)} "
        f"Q{fmt(right)},{fmt(bottom)} {fmt(right)},{fmt(bottom - corner)} "
        f"L{fmt(right)},{fmt(apex)} A{fmt(radius)},{fmt(radius)} 0 0 0 "
        f"{fmt(x)},{fmt(apex)} Z"
    )


def _k_label(value: float) -> str:
    """Axis label in thousands (``10k``)."""
    return f"{format_axis_number(value / _THOUSAND)}k"


def _flow_month(
    flow: MonthlyFlow, currency: str, scale: Scale, slot: tuple[int, float], *, is_now: bool
) -> FlowMonth:
    """One month; ``slot`` is its index and the shrink factor of a crowded row."""
    index, shrink = slot
    band_x = _FL_LEFT + (_FL_BAND_OFFSET + _FL_SLOT * index) * shrink
    first_of_month = date(flow.year, flow.month, 1)
    width = _FL_LOAF_W * shrink
    loaves: list[Loaf] = []
    tops: list[float] = []
    for amount, offset, is_expense in (
        (flow.income_minor, _FL_INCOME_OFFSET, False),
        (flow.expense_minor, _FL_EXPENSE_OFFSET, True),
    ):
        top = scale.y(major_float(amount, currency))
        tops.append(top)
        apex = min(top + width / 2, _FL_BOTTOM - _FL_CORNER)  # a loaf is never flatter than this
        d = _loaf_path(band_x + offset * shrink, width, apex) if amount > 0 else ""
        loaves.append(Loaf(d=d, is_expense=is_expense, is_now=is_now))
    center = band_x + _FL_LABEL_OFFSET * shrink
    income = format_figure(flow.income_minor, currency)
    expense = format_figure(flow.expense_minor, currency)
    net = format_figure(flow.income_minor - flow.expense_minor, currency, plus=True)
    tip_w, tip_h = _FL_TIP_SIZE
    lines = (
        f"{_month_abbr(first_of_month)} {flow.year}",
        f"in {income} {_DOT} out {expense}",
        f"net {net}",
    )
    return FlowMonth(
        aria_label=(
            f"{_month_label(first_of_month)}: income {income} {currency}, "
            f"expense {expense} {currency}"
        ),
        band_x=fmt(band_x),
        band_width=fmt(_FL_BAND_W * shrink),
        loaves=tuple(loaves),
        label_x=fmt(center),
        month=_month_abbr(first_of_month),
        year=str(flow.year),
        tooltip=_tooltip(
            _clamp(center - tip_w / 2, 0.0, _FL_WIDTH - tip_w),
            _clamp(min(tops) + _FL_TIP_GAP, 0.0, _FL_HEIGHT - tip_h),
            _FL_TIP_SIZE,
            lines,
        ),
    )


def _flow(aria_label: str, grid: tuple[GridLine, ...], months: tuple[FlowMonth, ...]) -> FlowChart:
    """A chart with the fixed plot frame around the variable parts."""
    return FlowChart(
        view_box=f"0 0 {_FL_WIDTH} {_FL_HEIGHT}",
        aria_label=aria_label,
        plot_left=_px(_FL_LEFT),
        plot_right=_px(_FL_WIDTH),
        plot_bottom=_px(_FL_BOTTOM),
        grid=grid,
        months=months,
    )


def _flow_span(months: Sequence[MonthlyFlow]) -> str:
    """``Jul to Oct 2026`` (years on both ends when the range crosses a year)."""
    first, last = months[0], months[-1]
    first_abbr = date(first.year, first.month, 1).strftime("%b")
    last_abbr = date(last.year, last.month, 1).strftime("%b")
    if first.year == last.year:
        return f"{first_abbr} to {last_abbr} {last.year}"
    return f"{first_abbr} {first.year} to {last_abbr} {last.year}"


def flow_chart(
    months: Sequence[MonthlyFlow], currency: str, *, current: tuple[int, int]
) -> FlowChart:
    """Geometry of the income-versus-expense loaves; ``current`` is the (year, month) in focus.

    A slot is 116 px wide with two 34 px loaves; more than four months shrink every x measure
    by the same factor so the row keeps fitting the 470 px plot.
    """
    if not months:
        return _flow("Monthly income and expense: no data.", (), ())
    top_value = max(
        max(major_float(m.income_minor, currency), major_float(m.expense_minor, currency))
        for m in months
    )
    low, high, tick_values = nice_scale(0.0, top_value) if top_value > 0 else (0.0, 1.0, (0.0, 1.0))
    scale = Scale(min(low, 0.0), high, _FL_TOP, _FL_BOTTOM)
    needed = _FL_BAND_OFFSET + _FL_SLOT * (len(months) - 1) + _FL_BAND_W
    shrink = min(1.0, (_FL_WIDTH - _FL_LEFT) / needed)
    return _flow(
        f"Monthly income and expense, {_flow_span(months)}. Hover a month for exact totals.",
        _grid(scale, tick_values, _k_label),
        tuple(
            _flow_month(m, currency, scale, (i, shrink), is_now=(m.year, m.month) == current)
            for i, m in enumerate(months)
        ),
    )
