"""The overlay's chart-geometry generator (T-UR12, ADR-0147 section 4).

The app's geometry functions reproduce the handoff charts exactly when fed the handoff's own
numbers (so a generated row can only come from a changed value), and a changed series yields
rows that apply cleanly and make the handoff chart equal the app chart.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from bs4 import BeautifulSoup

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services import analytics as analytics_service, fx as fx_service
from budget_planner.services.analytics import MonthlyFlow
from budget_planner.services.forecast import MonthlyProjectionPoint
from budget_planner import clock
from budget_planner.web import accounts_data, chart_geometry, plan_data
from budget_planner.web.accounts_view import AccountRow
from budget_planner.web.templating import build_jinja_env
from tests.visual import handoff_seed
from tests.visual.overlay import (
    APP_ONLY_ATTRIBUTES,
    FORECAST_CHART_ROOT,
    FORECAST_PAGE,
    GEOMETRY_ATTRIBUTES,
    GEOMETRY_SOURCES,
    OVERLAY_FILE,
    OverlayError,
    Row,
    apply_rows,
    geometry_rows,
    load_rows,
    same_geometry,
)

HANDOFF = Path(__file__).resolve().parents[2] / "docs" / "design" / "rising-dough-frontend"
FORECAST_HTML = (HANDOFF / FORECAST_PAGE).read_text(encoding="utf-8")
ANALYTICS_PAGE = "pages/plan/analytics.html"
ANALYTICS_HTML = (HANDOFF / ANALYTICS_PAGE).read_text(encoding="utf-8")
FLOW_ROOT = "section[aria-labelledby='ive-title']"
ACCOUNTS_PAGE = "pages/accounts.html"
ACCOUNTS_HTML = (HANDOFF / ACCOUNTS_PAGE).read_text(encoding="utf-8")
ACCOUNTS_GLOB = "pages/*.html"  # the accounts page and every overlay that shows it behind
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


# --- the committed rows (ADR-0147 section 4 amendment 2026-11-25) -------------------------

GEOMETRY_MARKER = "# --- generated geometry rows (do not edit; regenerate, see below) ---"
GEOMETRY_REASON = "geometry_rows from the base seed (ADR-0147 section 4 amendment 2026-11-25)"
DAY = dt.date(2026, 10, 31)
REGENERATE = "uv run python -m tests.visual.test_overlay_geometry"


def _seed_flow() -> tuple[MonthlyFlow, ...]:
    return _seed_charts_and_flow()[1]


def _seed_charts_and_flow() -> tuple[
    tuple[tuple[str, str, str, str], ...], tuple[MonthlyFlow, ...]
]:
    """(page, handoff html, root, app chart html) per chart, and the seed's monthly flow."""
    with tempfile.TemporaryDirectory() as tmp:
        result = handoff_seed.build_seed(Path(tmp) / "base.sqlite")
        settings = Settings(_env_file=None, database_url=f"sqlite:///{result.db_path.as_posix()}")
        conn = get_connection(settings)
        try:
            forecast = plan_data.forecast_page_for(
                conn, handoff_seed.OWNER_ID, settings, DAY, horizon=12, choices=(12,)
            )
            with clock.frozen(dt.datetime(2026, 10, 31, 10, tzinfo=dt.UTC)):
                page = accounts_data.hydrate(conn, handoff_seed.OWNER_ID, settings)
                trends = cast("list[AccountRow]", page["rows"])
            flow_months = analytics_service.bundle(
                conn,
                handoff_seed.OWNER_ID,
                fx_service.converter_for(conn, settings, DAY),
                today=DAY,
            ).income_vs_expense_monthly
        finally:
            conn.close()
    flow = chart_geometry.flow_chart(flow_months, "PLN", current=(2026, 10))
    charts = (
        (
            FORECAST_PAGE,
            FORECAST_HTML,
            FORECAST_CHART_ROOT,
            ENV.get_template("fragments/charts/forecast.html").render(chart=forecast.chart),
        ),
        (
            ANALYTICS_PAGE,
            ANALYTICS_HTML,
            FLOW_ROOT,
            ENV.get_template("fragments/charts/income-vs-expense.html").render(
                chart=flow, has_flow=True
            ),
        ),
    )
    return (*charts, *_account_trend_charts(trends)), flow_months


def _baked(svg: str) -> str:
    """The sparkline with its ``translate(0 N)`` margin added to the points (handoff: none)."""
    soup = BeautifulSoup(svg, "html.parser")
    for line in soup.select("polyline[transform]"):
        found = re.search(r"translate\(0 ([\d.]+)\)", str(line["transform"]))
        assert found is not None
        shift = float(found[1])
        pairs = (pair.split(",") for pair in str(line["points"]).split())
        line["points"] = " ".join(f"{float(x):.1f},{float(y) + shift:.2f}" for x, y in pairs)
        del line["transform"]
    return str(soup)


def _account_trend_charts(rows: Sequence[AccountRow]) -> tuple[tuple[str, str, str, str], ...]:
    """One chart per account row: the app's sparkline (``rd-account__trend`` cell) per row."""
    template = ENV.get_template("fragments/charts/sparkline.html")
    cells = "".join(
        f'<tr class="rd-row rd-row--account"><td class="rd-account__trend">'
        f"{_baked(template.render(spark=row.trend))}</td></tr>"
        for row in rows
    )
    app = f"<table><tbody>{cells}</tbody></table>"
    return tuple(
        (
            ACCOUNTS_PAGE,
            ACCOUNTS_HTML,
            f"tr.rd-row--account:nth-of-type({i}) td.rd-account__trend",
            app,
        )
        for i in range(1, len(rows) + 1)
    )


def seed_charts() -> tuple[tuple[str, str, str, str], ...]:
    return _seed_charts_and_flow()[0]


def seed_rows() -> tuple[Row, ...]:
    """Geometry rows for the forecast and flow charts, from the app run over the base seed."""
    return tuple(
        dataclasses.replace(row, page=ACCOUNTS_GLOB, optional=True) if page == ACCOUNTS_PAGE else row
        for page, html, root, app_html in seed_charts()
        for row in geometry_rows(page, html, root=root, app_html=app_html, reason=GEOMETRY_REASON)
    )


def rows_toml(rows: tuple[Row, ...]) -> str:
    """The marker line and one ``[[row]]`` block per geometry row (JSON strings are TOML's)."""
    blocks = [GEOMETRY_MARKER, ""]
    for r in rows:
        blocks += [
            "[[row]]",
            *(
                f"{key} = {json.dumps(getattr(r, key), ensure_ascii=False)}"
                for key in ("page", "select", "field", "old", "value", "reason", "source")
            ),
            *(["optional = true"] if r.optional else []),
            "",
        ]
    return "\n".join(blocks)


def _committed() -> tuple[Row, ...]:
    return tuple(r for r in load_rows() if r.source == "geometry")


@pytest.fixture(scope="module")
def generated() -> tuple[Row, ...]:
    return seed_rows()


def test_committed_rows_equal_the_generated_rows(generated: tuple[Row, ...]) -> None:
    assert generated, "the seed chart equals the handoff chart: no rows expected, none committed"
    assert _committed() == generated, f"stale geometry rows; regenerate with: {REGENERATE}"


def test_seed_chart_with_the_rows_equals_the_handoff_geometry(generated: tuple[Row, ...]) -> None:
    """Zero structural errors and exact coordinates once the committed rows are applied."""
    assert {r.page for r in generated} == {FORECAST_PAGE, ANALYTICS_PAGE, ACCOUNTS_GLOB}
    for page, html, root, app_html in seed_charts():
        applied = apply_rows(page, html, load_rows())
        assert applied != html
        # no structural error (OverlayError would raise) and nothing left to change
        assert geometry_rows(page, applied, root=root, app_html=app_html, reason="test") == ()


def test_the_seed_draws_the_boards_four_flow_months() -> None:
    flow = [m for m in _seed_flow() if (m.year, m.month) < (2026, 10)]

    assert [(m.year, m.month, m.income_minor, m.expense_minor) for m in flow] == [
        (m.year, m.month, m.income_minor, m.expense_minor) for m in HANDOFF_FLOW[:3]
    ]


if __name__ == "__main__":
    text = OVERLAY_FILE.read_text(encoding="utf-8")
    head = text.split(GEOMETRY_MARKER)[0].rstrip("\n")
    OVERLAY_FILE.write_text(f"{head}\n\n{rows_toml(seed_rows())}", encoding="utf-8")
