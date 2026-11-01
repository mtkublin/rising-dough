"""Plan hub — Rising Dough v2 (ADR-0051 §5).

Renders a tabbed shell (Budget · Year · Forecast · Analytics) with the
period header above tabs. Each tab assembles data from the existing
service helpers and renders a v2 template.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from budget_planner.config import Settings
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    forecast as forecast_service,
)
from budget_planner.web import charts
from budget_planner.web.deps import get_db, get_settings_dep
from budget_planner.web.rendering import render

router = APIRouter(tags=["plan"])

PlanTab = Literal["budget", "year", "forecast", "analytics"]
_VALID: tuple[PlanTab, ...] = ("budget", "year", "forecast", "analytics")
_VALID_PERIODS: tuple[analytics_service.Period, ...] = ("month", "year", "trailing-12")

_FORECAST_HORIZON_MONTHS = 12
_FORECAST_HORIZON_CHOICES: tuple[int, ...] = (6, 12, 24, 60)
_MINOR_UNITS_PER_MAJOR = 100.0
_MONTHS_IN_YEAR = 12


def _analytics_charts(bundle: analytics_service.AnalyticsBundle) -> dict[str, Any]:
    """Compute SVG geometry for the Analytics tab charts.

    Returns a dict with ``spend_chart`` (horizontal bars) and ``flow_chart``
    (grouped bars) so the template can render inline SVG without doing any
    math itself. All amounts converted to major units for display.
    """
    spend_items = tuple(
        (row.category_name, row.amount_minor / _MINOR_UNITS_PER_MAJOR)
        for row in bundle.spend_by_category
    )
    flow_groups = tuple(
        {
            "label": point.label[-5:],  # YYYY-MM → MM-?; keep tail for density
            "bars": [
                ("income", point.income_minor / _MINOR_UNITS_PER_MAJOR),
                ("expense", point.expense_minor / _MINOR_UNITS_PER_MAJOR),
            ],
        }
        for point in bundle.income_vs_expense_monthly
    )
    return {
        "spend_chart": charts.horizontal_bars(spend_items),
        "flow_chart": charts.grouped_bars(flow_groups),
    }


@router.get("/plan", response_class=HTMLResponse)
def plan(  # noqa: PLR0912, PLR0915 — one dispatcher per tab, kept flat for readability
    request: Request,
    tab: str = "budget",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    tab_norm: PlanTab = tab if tab in _VALID else "budget"
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    # Default landing month = fiscal cycle (ADR-0064). Falls back to the
    # calendar month when the anchor is unset or no promoted anchor-category
    # transaction exists on-or-before today.
    fiscal_year, fiscal_month = budget_service.fiscal_month_for(conn, today_d)
    year, month = fiscal_year, fiscal_month
    base_ccy = settings.base_currency

    # Budget + Analytics are month-scoped; allow ?year=&month= overrides so
    # the shared Plan selector can navigate prev/next month without extra
    # routes (manual-audit #32, #33).
    if tab_norm in {"budget", "analytics"}:
        try:
            month = int(request.query_params.get("month", month))
            year = int(request.query_params.get("year", year))
        except ValueError:
            year, month = fiscal_year, fiscal_month
        if not (1 <= month <= _MONTHS_IN_YEAR):
            year, month = fiscal_year, fiscal_month

    def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
        total = y * _MONTHS_IN_YEAR + (m - 1) + delta
        return total // _MONTHS_IN_YEAR, (total % _MONTHS_IN_YEAR) + 1

    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)

    ctx: dict[str, Any] = {
        "tab": tab_norm,
        "today": today_d,
        "year": year,
        "month": month,
        "base_ccy": base_ccy,
        "period_prev_year": prev_year,
        "period_prev_month": prev_month,
        "period_next_year": next_year,
        "period_next_month": next_month,
    }

    if tab_norm == "budget":
        import calendar as _cal  # noqa: PLC0415
        import dataclasses as _dc  # noqa: PLC0415

        from budget_planner.repositories import recurring as _rec_repo  # noqa: PLC0415
        from budget_planner.services import preferences as _prefs  # noqa: PLC0415

        # "Current" means the fiscal cycle anchored in (year, month)
        # contains today (ADR-0064). On the active cycle, keep anchor-window
        # math honest — spent runs from last_anchor_date through today. On
        # any other month, clamp spent to that calendar month (V.32).
        is_current = (year, month) == (fiscal_year, fiscal_month)
        if is_current:
            ref = today_d
            window_override: tuple[Any, Any] | None = None
        else:
            ref_last = _cal.monthrange(year, month)[1]
            ref = today_d.replace(year=year, month=month, day=min(today_d.day, ref_last))
            window_override = (
                today_d.replace(year=year, month=month, day=1),
                today_d.replace(year=year, month=month, day=ref_last),
            )
        summary = budget_service.month_summary(
            conn, year, month, today=ref, period_window=window_override
        )
        # For non-current months, override period_start + next_income_date so
        # the top bar reads anchor_day_in(month) → anchor_day_in(month+1).
        # Anchor day comes from the anchor category's active monthly recurring
        # rule; fall back to the first-of-month when no rule exists.
        if not is_current:
            anchor = _prefs.resolve_income_anchor_category(conn)
            anchor_day = 1
            if anchor is not None:
                for rule in _rec_repo.list_rules(conn, active_only=True):
                    if rule.category_id == anchor.id and rule.day_of_month:
                        anchor_day = max(1, min(28, rule.day_of_month))
                        break
            next_m_year, next_m = _shift_month(year, month, 1)
            start_day = min(anchor_day, _cal.monthrange(year, month)[1])
            end_day = min(anchor_day, _cal.monthrange(next_m_year, next_m)[1])
            new_start = ref.replace(year=year, month=month, day=start_day)
            new_end = ref.replace(year=next_m_year, month=next_m, day=end_day)
            # Future month: show full period length; past month: 0.
            days_left = (new_end - new_start).days if new_end > today_d else 0
            # Future months: no commitments yet; past months: commitments
            # already landed as actuals. Either way, committed_total shown
            # by month_summary (uses real "today → next_income") doesn't
            # apply to the picker. Zero it out + rebuild totals.
            new_committed = 0
            new_remaining = summary.totals.budgeted_minor - summary.totals.spent_minor
            new_totals = _dc.replace(
                summary.totals,
                committed_minor=new_committed,
                remaining_minor=new_remaining,
            )
            summary = _dc.replace(
                summary,
                totals=new_totals,
                period_start=new_start,
                next_income_date=new_end,
                days_until_next_income=days_left,
            )
        ctx["summary"] = summary
    elif tab_norm == "year":
        year_param = request.query_params.get("year")
        selected_year = year
        if year_param is not None:
            try:
                selected_year = int(year_param)
            except ValueError:
                selected_year = year
        rows = budget_service.yearly_grid(conn, selected_year)
        column_totals = [sum((r.cells[i].amount_minor or 0) for r in rows) for i in range(12)]
        grand_total = sum(r.total_minor for r in rows)
        ctx["year_rows"] = rows
        ctx["year_selected"] = selected_year
        ctx["year_column_totals"] = column_totals
        ctx["year_grand_total"] = grand_total
    elif tab_norm == "forecast":
        horizon_raw = request.query_params.get("horizon", str(_FORECAST_HORIZON_MONTHS))
        try:
            horizon = int(horizon_raw)
        except ValueError:
            horizon = _FORECAST_HORIZON_MONTHS
        if horizon not in _FORECAST_HORIZON_CHOICES:
            horizon = _FORECAST_HORIZON_MONTHS
        projection = forecast_service.monthly_projection(conn, settings, today_d, horizon=horizon)
        ctx["forecast_points"] = projection
        ctx["forecast_horizon"] = horizon
        ctx["forecast_horizon_choices"] = _FORECAST_HORIZON_CHOICES
        chart_points = tuple((float(i), p.value_major) for i, p in enumerate(projection))
        chart_labels = tuple(p.label for p in projection)
        ctx["forecast_chart"] = charts.line_area(chart_points, x_labels=chart_labels)
        # Summary strip: NOW / END / PEAK.
        if projection:
            start_value = projection[0].value_major
            end_point = projection[-1]
            peak_point = max(projection, key=lambda p: p.value_major)
            ctx["forecast_summary"] = {
                "now_value": start_value,
                "end_point": end_point,
                "peak_point": peak_point,
            }
        else:
            ctx["forecast_summary"] = None
    else:
        period_raw = request.query_params.get("period", "month")
        period_norm: analytics_service.Period = "month"
        for candidate in _VALID_PERIODS:
            if period_raw == candidate:
                period_norm = candidate
                break
        # Analytics month selector feeds the service a synthetic "today"
        # anchored to the selected month-end so period math respects the
        # picker instead of pinning to real today.
        import calendar as _cal  # noqa: PLC0415

        if (year, month) == (today_d.year, today_d.month):
            ref_today = today_d
        else:
            ref_last = _cal.monthrange(year, month)[1]
            ref_today = today_d.replace(year=year, month=month, day=ref_last)
        bundle = analytics_service.bundle(conn, today=ref_today, period=period_norm)
        ctx["bundle"] = bundle
        ctx["period"] = period_norm
        # Build a `category_id → 12-mo avg minor` map so the Spend-by-category
        # list can show a signed "vs 12-mo avg" delta without an extra pass.
        ctx["twelve_mo_avg_by_cat"] = {
            row.category_id: row.amount_minor for row in bundle.twelve_month_averages
        }
        ctx["spend_total_minor"] = sum(r.amount_minor for r in bundle.spend_by_category)
        ctx.update(_analytics_charts(bundle))

    return render(request, "plan/index.html", **ctx)


@router.get("/plan/analytics", response_class=HTMLResponse)
def plan_analytics(
    request: Request,
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """ADR-0056 §6 — four-panel analytics bundle for the Analytics tab.

    ``period`` controls spend-by-category + largest-items window; the
    averages + flow trend always span the trailing 12 months.
    """
    period_norm: analytics_service.Period = "month"
    for candidate in _VALID_PERIODS:
        if period == candidate:
            period_norm = candidate
            break
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    data = analytics_service.bundle(conn, today=today_d, period=period_norm)
    return render(
        request,
        "plan/_analytics_bundle.html",
        bundle=data,
        base_ccy=settings.base_currency,
        period=period_norm,
        **_analytics_charts(data),
    )


@router.get("/budget-legacy", include_in_schema=False)
def _redirect_budget() -> RedirectResponse:
    return RedirectResponse(url="/plan?tab=budget", status_code=302)
