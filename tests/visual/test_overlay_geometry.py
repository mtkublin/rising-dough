"""The overlay's chart-geometry generator (T-UR12, ADR-0147 section 4).

The app's geometry functions reproduce the handoff charts exactly when fed the handoff's own
numbers (so a generated row can only come from a changed value), and a changed series yields
rows that apply cleanly and make the handoff chart equal the app chart.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.services.analytics import MonthlyFlow
from budget_planner.services.forecast import MonthlyProjectionPoint
from budget_planner.web import chart_geometry
from budget_planner.web.templating import build_jinja_env
from tests.visual.overlay import (
    APP_ONLY_ATTRIBUTES,
    FORECAST_CHART_ROOT,
    FORECAST_PAGE,
    GEOMETRY_ATTRIBUTES,
    GEOMETRY_SOURCES,
    OverlayError,
    Row,
    apply_rows,
    geometry_rows,
    same_geometry,
)

HANDOFF = Path(__file__).resolve().parents[2] / "docs" / "design" / "rising-dough-frontend"
FORECAST_HTML = (HANDOFF / FORECAST_PAGE).read_text(encoding="utf-8")
ANALYTICS_PAGE = "pages/plan/analytics.html"
ANALYTICS_HTML = (HANDOFF / ANALYTICS_PAGE).read_text(encoding="utf-8")
FLOW_ROOT = "section[aria-labelledby='ive-title']"
MINUS = "\N{MINUS SIGN}"
ENV = build_jinja_env(Settings(_env_file=None))

# The handoff's twelve months (pages/plan/forecast.html): end balance and net, in minor units.
HANDOFF_SERIES = (
    (3_272_722, -171_247),
    (3_467_979, 195_257),
    (3_295_577, -172_402),
    (3_457_488, 161_911),
    (4_255_538, 798_050),
    (6_778_979, 2_523_441),
    (7_035_682, 256_703),
    (7_817_635, 781_953),
    (8_101_351, 283_716),
    (8_362_659, 261_308),
    (8_623_967, 261_308),
    (7_904_779, -719_188),
)
# The handoff's four months of income and expense (pages/plan/analytics.html).
HANDOFF_FLOW = (
    MonthlyFlow(2026, 7, 2_141_206, 2_235_418),
    MonthlyFlow(2026, 8, 2_201_840, 2_520_177),
    MonthlyFlow(2026, 9, 2_137_795, 2_604_012),
    MonthlyFlow(2026, 10, 2_234_110, 1_941_718),
)


def _points(series: tuple[tuple[int, int], ...]) -> tuple[MonthlyProjectionPoint, ...]:
    months = [dt.date(2026 + (9 + i) // 12, (9 + i) % 12 + 1, 1) for i in range(len(series))]
    return tuple(
        MonthlyProjectionPoint(
            month=m, label=m.strftime("%b %Y"), end_balance_minor=balance, net_minor=net
        )
        for m, (balance, net) in zip(months, series, strict=True)
    )


def _forecast_html(series: tuple[tuple[int, int], ...]) -> str:
    chart = chart_geometry.forecast_chart(
        _points(series), "PLN", caption_prefix="PROJECTED BALANCE"
    )
    return ENV.get_template("fragments/charts/forecast.html").render(chart=chart)


def _flow_html(months: tuple[MonthlyFlow, ...]) -> str:
    chart = chart_geometry.flow_chart(months, "PLN", current=(2026, 10))
    return ENV.get_template("fragments/charts/income-vs-expense.html").render(
        chart=chart, has_flow=bool(months)
    )


def _forecast_rows(series: tuple[tuple[int, int], ...]) -> tuple[Row, ...]:
    return geometry_rows(
        FORECAST_PAGE,
        FORECAST_HTML,
        root=FORECAST_CHART_ROOT,
        app_html=_forecast_html(series),
        reason="test",
    )


def test_geometry_source_is_registered() -> None:
    assert "geometry" in GEOMETRY_SOURCES
    assert {"x1", "x2", "y1", "y2", "points", "d"} <= GEOMETRY_ATTRIBUTES


def test_same_geometry_ignores_formatting_only() -> None:
    assert same_geometry("72.0", "72.000")
    assert same_geometry("M76.0,246.0 Q76.0,250.0", "M76.000,246.000 Q76.000,250.000")
    assert not same_geometry("72.0", "72.1")
    assert not same_geometry("M1,2 L3,4", "M1,2 Q3,4")


def test_forecast_chart_matches_the_handoff_for_the_handoff_series() -> None:
    assert _forecast_rows(HANDOFF_SERIES) == ()


def test_flow_chart_matches_the_handoff_for_the_handoff_months() -> None:
    rows = geometry_rows(
        ANALYTICS_PAGE,
        ANALYTICS_HTML,
        root=FLOW_ROOT,
        app_html=_flow_html(HANDOFF_FLOW),
        reason="test",
    )

    assert rows == ()


def test_a_changed_balance_generates_rows_that_make_the_chart_equal() -> None:
    changed = (*HANDOFF_SERIES[:-1], (5_876_115, -2_028_664))  # the seed's Sep 2027

    rows = _forecast_rows(changed)

    assert rows
    assert {r.source for r in rows} == {"geometry"}
    assert {r.page for r in rows} == {FORECAST_PAGE}
    fields = {r.field for r in rows}
    assert {"cy", "points", "aria-label", "text"} <= fields
    dot = [r for r in rows if r.field == "aria-label"]
    assert [r.value for r in dot] == [f"Sep 2027: 58,761.15 PLN, net {MINUS}20,286.64"]
    applied = apply_rows(FORECAST_PAGE, FORECAST_HTML, rows)
    assert (
        geometry_rows(
            FORECAST_PAGE,
            applied,
            root=FORECAST_CHART_ROOT,
            app_html=_forecast_html(changed),
            reason="test",
        )
        == ()
    )


def test_a_changed_scale_relabels_the_axis_and_moves_the_dots() -> None:
    changed = tuple((b // 2, n) for b, n in HANDOFF_SERIES)

    rows = _forecast_rows(changed)

    assert {r.field for r in rows} == {"aria-label", "text"}  # same relative shape, new numbers
    labels = [r.value for r in rows if r.field == "text" and r.value.replace(",", "").isdigit()]
    assert labels == ["10,000", "20,000", "30,000", "40,000", "50,000"]


def test_a_different_month_count_is_a_structural_error() -> None:
    with pytest.raises(OverlayError, match="61 child elements, the app draws 57"):
        _forecast_rows(HANDOFF_SERIES[:-1])


def test_flow_rows_follow_changed_amounts() -> None:
    changed = (*HANDOFF_FLOW[:-1], dataclasses.replace(HANDOFF_FLOW[-1], expense_minor=2_900_000))

    rows = geometry_rows(
        ANALYTICS_PAGE,
        ANALYTICS_HTML,
        root=FLOW_ROOT,
        app_html=_flow_html(changed),
        reason="test",
    )

    assert {"d", "aria-label"} <= {r.field for r in rows}
    labels = [r.value for r in rows if r.field == "aria-label"]
    assert labels == ["Oct 2026: income 22,341.10 PLN, expense 29,000.00 PLN"]


def test_derived_attributes_pass_only_on_the_listed_element() -> None:
    app = _forecast_html(HANDOFF_SERIES)
    assert 'role="region"' in app  # the scroll container carries its derived attributes
    stray = app.replace(
        '<line class="rd-chart__guide"', '<line aria-label="x" class="rd-chart__guide"', 1
    )

    with pytest.raises(OverlayError, match="attribute 'aria-label' is missing on one side"):
        geometry_rows(
            FORECAST_PAGE, FORECAST_HTML, root=FORECAST_CHART_ROOT, app_html=stray, reason="test"
        )
    assert "div.rd-chart-card__plot" in APP_ONLY_ATTRIBUTES
