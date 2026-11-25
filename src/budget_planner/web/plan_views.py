"""Plan forecast and analytics view models (T-UR12, ADR-0107 section 5).

Everything the two pages print is computed here from service values: hero text, horizon and
range buttons, table rows with their sign marks, share bars, deltas, ledger links and the chart
geometry (``chart_geometry``). Templates only print. No I/O, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from budget_planner.domain.money import format_figure, percent_of
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    forecast as forecast_service,
)
from budget_planner.web import chart_geometry
from budget_planner.web.view_models import (
    BAR_FILLED,
    BAR_LEFT,
    MONTH_SHORT,
    BudgetPeriod,
    bar_cells,
    day_month,
    month_period,
    period_note,
)

# --- Plan forecast (T-UR12) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ForecastRowView:
    """One month of the forecast table; ``net_text`` carries the sign, ``net_negative`` the mark."""

    month: date
    label: str
    income_minor: int
    expense_minor: int
    planned_budget_minor: int
    net_text: str
    net_negative: bool
    end_balance_minor: int
    balance_text: str


@dataclass(frozen=True, slots=True)
class HorizonOption:
    """One horizon button (months) and whether it is the selected one."""

    months: int
    pressed: bool
    url: str


@dataclass(frozen=True, slots=True)
class ForecastPageView:
    """Hero, chart and table values of Plan · forecast."""

    hero_label: str
    hero_balance_minor: int
    hero_note: str
    horizon: int
    options: tuple[HorizonOption, ...]
    rows: tuple[ForecastRowView, ...]
    chart: chart_geometry.ForecastChart


def _month_year_lower(month: date) -> str:
    """``sep 2027``: the handoff's lower-case short month and year."""
    return f"{MONTH_SHORT[month.month - 1].lower()} {month.year}"


def forecast_hero_note(summary: forecast_service.ProjectionSummary, currency: str) -> str:
    """``+46,320.57 PLN over 12 months · peak 86,239.67 in aug 2027`` from the summary strip."""
    signed = {
        forecast_service.TrendDirection.UP: summary.delta_minor,
        forecast_service.TrendDirection.DOWN: -summary.delta_minor,
        forecast_service.TrendDirection.FLAT: 0,
    }[summary.delta_direction]
    noun = "month" if summary.months == 1 else "months"
    peak = format_figure(summary.peak_point.end_balance_minor, currency)
    return (
        f"{format_figure(signed, currency, plus=True)} {currency} over {summary.months} {noun}"
        f" · peak {peak} in {_month_year_lower(summary.peak_point.month)}"
    )


def forecast_page(
    projection: tuple[forecast_service.MonthlyProjectionPoint, ...],
    summary: forecast_service.ProjectionSummary | None,
    *,
    horizon: int,
    choices: tuple[int, ...],
    currency: str,
    base_url: str,
) -> ForecastPageView:
    """Forecast page values; ``base_url`` ends in ``horizon=`` for the horizon buttons."""
    rows = tuple(
        ForecastRowView(
            month=p.month,
            label=p.label,
            income_minor=p.income_minor,
            expense_minor=p.expense_minor,
            planned_budget_minor=p.planned_budget_minor,
            net_text=format_figure(p.net_minor, currency),
            net_negative=p.net_minor < 0,
            end_balance_minor=p.end_balance_minor,
            balance_text=format_figure(p.end_balance_minor, currency),
        )
        for p in projection
    )
    return ForecastPageView(
        hero_label=(
            f"projected balance · end of {_month_year_lower(summary.end_point.month)}"
            if summary
            else "projected balance"
        ),
        hero_balance_minor=summary.end_point.end_balance_minor if summary else 0,
        hero_note=forecast_hero_note(summary, currency) if summary else "",
        horizon=horizon,
        options=tuple(HorizonOption(h, h == horizon, f"{base_url}{h}") for h in choices),
        rows=rows,
        chart=chart_geometry.forecast_chart(
            projection, currency, caption_prefix="PROJECTED BALANCE"
        ),
    )


# --- Plan analytics (T-UR12) -------------------------------------------------

_SPEND_BAR_CELLS: Final = 20
_RANGE_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("month", "month"),
    ("year", "year to date"),
    ("trailing-12", "12 months"),
)


@dataclass(frozen=True, slots=True)
class SpendRowView:
    """One spend-by-category row: share bar, ledger link and the 12-month delta."""

    category_id: int
    category_name: str
    category_color: str | None
    amount_minor: int
    share_pct: int
    bar_filled: str
    bar_rest: str
    link_label: str
    ledger_url: str
    has_average: bool
    delta_text: str
    delta_down: bool


def ledger_url_for(category_id: int, start: date, end: date) -> str:
    """Ledger link that opens the category's actuals inside the analytics window."""
    return (
        f"/ledger?view=actual&category_id={category_id}"
        f"&date_from={start.isoformat()}&date_to={end.isoformat()}"
    )


def spend_rows(
    bundle: analytics_service.AnalyticsBundle,
    averages: Mapping[int, int],
    colors: Mapping[int, str | None],
    currency: str,
) -> tuple[SpendRowView, ...]:
    """Spend rows with share of the period total, block bar and delta vs the 12-month average."""
    total = analytics_service.spend_total_minor(bundle)
    out: list[SpendRowView] = []
    for row in bundle.spend_by_category:
        share = percent_of(row.amount_minor, total)
        # a non-zero amount always shows at least one filled cell (the handoff's 20-cell rule)
        cells = bar_cells(
            max(share, 1) if row.amount_minor > 0 else 0, _SPEND_BAR_CELLS, min_one=True
        )
        avg = averages.get(row.category_id, 0)
        delta = row.amount_minor - avg
        has_average = avg > 0 and delta != 0
        out.append(
            SpendRowView(
                category_id=row.category_id,
                category_name=row.category_name,
                category_color=colors.get(row.category_id),
                amount_minor=row.amount_minor,
                share_pct=share,
                bar_filled=BAR_FILLED * cells.filled,
                bar_rest=BAR_LEFT * cells.empty,
                link_label=(
                    f"{row.category_name}: {format_figure(row.amount_minor, currency)} "
                    f"{currency}, open in ledger"
                ),
                ledger_url=ledger_url_for(row.category_id, bundle.period_start, bundle.period_end),
                has_average=has_average,
                delta_text=(
                    f"{'▲' if delta > 0 else '▼'} {format_figure(delta, currency, plus=True)}"
                    if has_average
                    else "—"
                ),
                delta_down=delta < 0,
            )
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class RangeOption:
    """One range button (month, year to date, 12 months)."""

    label: str
    pressed: bool
    url: str


@dataclass(frozen=True, slots=True)
class LargestItemView:
    """One of the largest single items: category, ``15 Oct`` and the signed amount."""

    name: str
    date_text: str
    amount_text: str
    url: str


@dataclass(frozen=True, slots=True)
class AnalyticsPageView:
    """Hero, range buttons, spend table, flow chart and largest items of Plan · analytics."""

    hero_total_minor: int
    ranges: tuple[RangeOption, ...]
    rows: tuple[SpendRowView, ...]
    flow: chart_geometry.FlowChart
    has_flow: bool
    largest: tuple[LargestItemView, ...]
    period: BudgetPeriod


def analytics_period(
    picked: budget_service.PickerMonth, bundle: analytics_service.AnalyticsBundle
) -> BudgetPeriod:
    """Period nav for the analytics tab; the picker note shows the window being summed."""
    start, end = bundle.period_start, bundle.period_end
    if bundle.period == "month":
        note = period_note(picked.month, start, end)
    else:
        label = dict(_RANGE_LABELS)[bundle.period]
        note = f"{label} = {day_month(start)} → {day_month(end)}"
    return month_period(
        picked,
        picker_id="period-analytics",
        note=note,
        base_url=f"/plan?tab=analytics&period={bundle.period}",
    )


def analytics_page(
    bundle: analytics_service.AnalyticsBundle,
    picked: budget_service.PickerMonth,
    colors: Mapping[int, str | None],
    currency: str,
) -> AnalyticsPageView:
    """Analytics page values for the picked month and the bundle's range."""
    query = f"&year={picked.year}&month={picked.month}"
    return AnalyticsPageView(
        hero_total_minor=analytics_service.spend_total_minor(bundle),
        ranges=tuple(
            RangeOption(label, value == bundle.period, f"/plan?tab=analytics&period={value}{query}")
            for value, label in _RANGE_LABELS
        ),
        rows=spend_rows(
            bundle, analytics_service.twelve_month_avg_by_category(bundle), colors, currency
        ),
        flow=chart_geometry.flow_chart(
            bundle.income_vs_expense_monthly, currency, current=(picked.year, picked.month)
        ),
        has_flow=bool(bundle.income_vs_expense_monthly),
        largest=tuple(
            LargestItemView(
                name=item.category_name,
                date_text=f"{item.operation_date.day} {MONTH_SHORT[item.operation_date.month - 1]}",
                amount_text=format_figure(-item.amount_minor, currency),
                url=(
                    f"/ledger?view=actual&date_from={item.operation_date.isoformat()}"
                    f"&date_to={item.operation_date.isoformat()}"
                ),
            )
            for item in bundle.largest_items
        ),
        period=analytics_period(picked, bundle),
    )
