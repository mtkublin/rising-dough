"""T-UR03: category colour presets, contrast math and edge computation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from budget_planner.domain import category_colors as cc

_CSS = (
    Path(__file__).resolve().parents[3]
    / "src/budget_planner/web/static/rd/css/components/category-colors.css"
)


def _css_presets() -> list[tuple[str, str, str]]:
    return re.findall(
        r'data-color="(\w+)"\]\s*\{\s*--cat:\s*(#\w+);\s*--cat-edge:\s*(#\w+);', _CSS.read_text()
    )


def test_category_color_presets_equal_css() -> None:
    assert [(p.name, p.cat, p.edge) for p in cc.PRESETS] == _css_presets()
    assert len(cc.PRESETS) == 29  # 30 presets minus grey (a var(), no hex)


@pytest.mark.parametrize("preset", cc.PRESETS, ids=lambda p: p.name)
def test_category_color_preset_round_trip(preset: cc.CategoryPreset) -> None:
    for spelled in (preset.cat, preset.cat.upper()):
        result = cc.category_color(spelled)
        assert (result.name, result.cat, result.edge, result.custom) == (
            preset.name,
            preset.cat,
            preset.edge,
            False,
        )
        assert result.rule == ""


def test_category_color_none_is_neutral() -> None:
    for empty in (None, ""):
        result = cc.category_color(empty)
        assert (result.name, result.cat, result.edge, result.custom) == (None, None, None, False)
        assert result.rule == ""


def test_category_color_custom_dark_keeps_hue() -> None:
    result = cc.category_color("#123456")
    assert (result.name, result.edge, result.custom) == ("c-123456", "#123456", True)
    assert result.rule == '[data-color="c-123456"]{--cat:#123456;--cat-edge:#123456}'


def test_category_color_custom_light_is_darkened() -> None:
    result = cc.category_color("#FFCC00")
    assert (result.name, result.cat, result.edge) == ("c-ffcc00", "#ffcc00", "#ad8a00")
    assert result.rule == '[data-color="c-ffcc00"]{--cat:#ffcc00;--cat-edge:#ad8a00}'
    assert cc.contrast_ratio("#ad8a00", cc.PANEL_BACKGROUND) >= 3.0


def test_category_color_second_custom_edge_exact() -> None:
    assert cc.category_color("#ffee99").edge == cc.edge_color("#ffee99")
    assert cc.edge_color("#ffee99") == "#998f5c"


@pytest.mark.parametrize("hue", ["#ffffff", "#ffee99", "#ff00ff", "#00ffff", "#abcdef"])
def test_category_color_edge_contrast_at_least_three(hue: str) -> None:
    assert cc.contrast_ratio(cc.edge_color(hue), cc.PANEL_BACKGROUND) >= 3.0


def test_contrast_extremes() -> None:
    assert cc.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert cc.relative_luminance("#ffffff") == pytest.approx(1.0)
    assert cc.relative_luminance("#000000") == 0.0
    assert cc.relative_luminance("#010101") == pytest.approx(1 / 255 / 12.92)


def test_edge_color_falls_back_to_black_on_dark_background() -> None:
    # On a dark panel no scaled-down hue reaches 3:1 (even black is below), so black is returned.
    assert cc.edge_color("#404040", "#404040") == "#000000"
