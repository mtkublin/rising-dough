"""T-UR03: bar spans, year-cell state, aria labels and their Jinja filters."""

from __future__ import annotations

import pytest

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.web import view_models
from budget_planner.web.templating import build_jinja_env

FULL = "█"
LEFT = "░"
REST = "▒"


@pytest.mark.parametrize(
    ("used", "left", "label"),
    [(78, 15, "78 percent spent, 15 percent left"), (0, 100, "0 percent spent, 100 percent left")],
)
def test_bar_aria_label(used: int, left: int, label: str) -> None:
    assert view_models.bar_aria_label(used, left) == label


@pytest.mark.parametrize(
    ("direction", "label"),
    [
        (Direction.EXPENSE, "\u2193 expense"),
        (Direction.INCOME, "\u2191 income"),
        (Direction.TRANSIT, "\u21c4 transit"),
        (Direction.ADJUSTMENT, "\u00b1 adjustment"),
    ],
)
def test_direction_label(direction: Direction, label: str) -> None:
    assert view_models.direction_label(direction) == label


def test_bar_spans_zero_percent() -> None:
    assert view_models.bar_spans(0, 10) == view_models.BarSpans(
        modifier="",
        filled="",
        remainder=LEFT * 10,
        remainder_class="rd-bar__left",
        left_pct=100,
        label="0 percent spent, 100 percent left",
    )


def test_bar_spans_full_not_over() -> None:
    spans = view_models.bar_spans(100, 10)
    assert (spans.modifier, spans.filled, spans.remainder, spans.left_pct) == ("", FULL * 10, "", 0)
    assert spans.label == "100 percent spent, 0 percent left"


def test_bar_spans_partial_min_one_20_cells() -> None:
    spans = view_models.bar_spans(78, 20, min_one=True)
    assert (spans.filled, spans.remainder) == (FULL * 16, LEFT * 4)
    assert spans.label == "78 percent spent, 22 percent left"


def test_bar_spans_over_budget() -> None:
    spans = view_models.bar_spans(130, 10, is_over=True)
    assert (spans.modifier, spans.filled, spans.remainder, spans.left_pct) == (
        "rd-bar--over",
        FULL * 10,
        "",
        0,
    )
    assert spans.label == "130 percent spent, 0 percent left"


def test_bar_spans_none() -> None:
    spans = view_models.bar_spans(0, 20, has_budget=False)
    assert (spans.modifier, spans.filled, spans.remainder, spans.label) == (
        "rd-bar--none",
        "",
        LEFT * 20,
        "no budget",
    )


def test_bar_spans_share_uses_rest_shade() -> None:
    spans = view_models.bar_spans(39, 10, share=True)
    assert (spans.filled, spans.remainder, spans.remainder_class) == (
        FULL * 4,
        REST * 6,
        "rd-bar__rest",
    )
    assert view_models.bar_spans(0, 4, has_budget=False, share=True).remainder == REST * 4


@pytest.mark.parametrize(
    ("origin", "editing", "state"),
    [
        ("default", False, "default"),
        ("recurring", False, "recurring"),
        ("one_off", False, "one-off"),
        ("unset", False, "unset"),
        (None, False, "default"),
        ("bogus", False, "default"),
        ("recurring", True, "editing"),
    ],
)
def test_year_cell_state(origin: str | None, editing: bool, state: str) -> None:
    assert view_models.year_cell_state(origin, editing=editing) == state


def _render(template: str, **context: object) -> str:
    return build_jinja_env(Settings()).from_string(template).render(**context)


def test_filter_category_color_preset_and_custom() -> None:
    tpl = "{% set c = v | category_color %}{{ c.name }}|{{ c.edge }}|{{ c.rule | safe }}"
    assert _render(tpl, v="#ff9f43") == "orange|#c77c34|"
    assert _render(tpl, v="#ffcc00") == (
        'c-ffcc00|#ad8a00|[data-color="c-ffcc00"]{--cat:#ffcc00;--cat-edge:#ad8a00}'
    )


def test_filter_bar_spans_and_label() -> None:
    assert _render("{% set b = 39 | bar_spans(10) %}{{ b.filled }}{{ b.remainder }}") == (
        FULL * 4 + LEFT * 6
    )
    assert _render("{{ 78 | bar_aria_label(15) }}") == "78 percent spent, 15 percent left"


def test_filter_direction_label() -> None:
    assert _render("{{ 'income' | direction_label }}") == "\u2191 income"
    assert _render("{{ d | direction_label }}", d=Direction.TRANSIT) == "\u21c4 transit"


def test_filter_year_cell_state() -> None:
    assert _render("{{ 'one_off' | year_cell_state }}") == "one-off"
    assert _render("{{ 'one_off' | year_cell_state(editing=true) }}") == "editing"


def test_filter_aria_current_date() -> None:
    assert _render("{{ true | aria_current_date }}") == 'aria-current="date"'
    assert _render("{{ false | aria_current_date }}") == ""
