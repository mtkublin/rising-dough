"""ADR-0048 — category_label helper."""

from __future__ import annotations

from dataclasses import dataclass

from budget_planner.domain.enums import Direction
from budget_planner.web.templating import (
    _category_label,
    _category_label_parts,
    _direction_badge,
    _resolve_category_color,
)


@dataclass(frozen=True)
class _Cat:
    name: str
    direction: Direction
    color: str | None = None


def test_resolve_direction_default_income() -> None:
    assert _resolve_category_color(Direction.INCOME, None) == "var(--income)"


def test_resolve_direction_default_expense() -> None:
    assert _resolve_category_color(Direction.EXPENSE, None) == "var(--expense)"


def test_resolve_override_hex_wins() -> None:
    assert _resolve_category_color(Direction.EXPENSE, "#112233") == "#112233"


def test_resolve_unknown_direction_falls_back_to_adjust() -> None:
    assert _resolve_category_color(None, None) == "var(--adjust)"


def test_category_label_wraps_name_in_pill() -> None:
    html = str(_category_label(_Cat(name="Food", direction=Direction.EXPENSE)))
    assert 'class="pill cat-pill"' in html
    assert "color: var(--expense)" in html
    assert "color-mix(in oklab, var(--expense) 16%, transparent)" in html
    assert ">Food<" in html


def test_category_label_uses_override_hex() -> None:
    html = str(_category_label(_Cat(name="Rent", direction=Direction.EXPENSE, color="#aabbcc")))
    assert "color: #aabbcc" in html
    assert "color-mix(in oklab, #aabbcc 16%, transparent)" in html


def test_category_label_handles_none() -> None:
    assert str(_category_label(None)) == ""


def test_category_label_parts_empty_name_renders_nothing() -> None:
    assert str(_category_label_parts(None, Direction.EXPENSE, None)) == ""
    assert str(_category_label_parts("", Direction.EXPENSE, None)) == ""


def test_category_label_escapes_name() -> None:
    html = str(_category_label(_Cat(name="<img src=x onerror=1>", direction=Direction.EXPENSE)))
    assert "<img" not in html
    assert "&lt;img" in html


def test_direction_badge_escapes_unknown_value() -> None:
    html = str(_direction_badge('<b>"x'))
    assert "<b>" not in html
    escaped = "&lt;b&gt;&#34;x"
    assert html == f'<span class="pill pill-adjust" aria-label="{escaped}">{escaped}</span>'
