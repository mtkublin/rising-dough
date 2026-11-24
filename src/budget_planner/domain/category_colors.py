"""Category colour presets and the ``--cat-edge`` contrast computation (T-UR03, ADR-0107 §5).

The handoff styles a category chip through ``data-color="<name>"``. A stored hex
equal to a preset's ``--cat`` maps to that preset's name; any other hue gets a
generated name and a rule whose ``--cat-edge`` is the hue scaled down until it
holds 3:1 contrast on the light panel colour. Pure: no I/O, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PANEL_BACKGROUND: Final = "#faf7f3"
"""``--color-panel`` (light theme): the surface the edge must hold ``MIN_EDGE_CONTRAST`` on."""
MIN_EDGE_CONTRAST: Final = 3.0
_SCALE_BITS: Final = 7
_SCALE_STEPS: Final = 1 << _SCALE_BITS
_CHANNEL_MAX: Final = 255
_SRGB_LINEAR_CUTOFF: Final = 0.03928
_LUMA_WEIGHTS: Final = (0.2126, 0.7152, 0.0722)


@dataclass(frozen=True, slots=True)
class CategoryPreset:
    """One ``[data-color]`` preset of ``category-colors.css`` (hex values only)."""

    name: str
    cat: str
    edge: str


# Mirrors category-colors.css (a unit test compares both). ``grey`` is the neutral
# default (``var(--color-ink-muted)``), so it has no hex and is not listed.
PRESETS: Final[tuple[CategoryPreset, ...]] = (
    CategoryPreset("coral", "#ff8a8a", "#d17171"),
    CategoryPreset("orange", "#ff9f43", "#c77c34"),
    CategoryPreset("gold", "#f5c542", "#ab8a2e"),
    CategoryPreset("lime", "#a3e635", "#6f9c24"),
    CategoryPreset("chartreuse", "#bef264", "#76963e"),
    CategoryPreset("mint", "#86efac", "#589e72"),
    CategoryPreset("emerald", "#34d399", "#28a074"),
    CategoryPreset("teal", "#2dd4bf", "#219d8d"),
    CategoryPreset("aqua", "#6ee7d3", "#4b9d8f"),
    CategoryPreset("cyan", "#4fd1e8", "#3a9bac"),
    CategoryPreset("sky", "#38bdf8", "#2d97c6"),
    CategoryPreset("blue", "#5b8cff", "#5989fa"),
    CategoryPreset("violet", "#c77dff", "#b370e5"),
    CategoryPreset("periwinkle", "#94a3ff", "#7c89d6"),
    CategoryPreset("orchid", "#f0abfc", "#ad7bb5"),
    CategoryPreset("rose", "#fb7185", "#e26678"),
    CategoryPreset("peach", "#fdba74", "#b68654"),
    CategoryPreset("seafoam", "#7be0a8", "#569d76"),
    CategoryPreset("pink", "#ff7ab6", "#db699d"),
    CategoryPreset("silver", "#e2e8f0", "#8c9095"),
    CategoryPreset("red", "#ef4444", "#ef4444"),
    CategoryPreset("tangerine", "#f97316", "#e56a14"),
    CategoryPreset("yellow", "#eab308", "#b28806"),
    CategoryPreset("leaf", "#84cc16", "#679f11"),
    CategoryPreset("green", "#22c55e", "#1da54f"),
    CategoryPreset("jade", "#14b8a6", "#11a090"),
    CategoryPreset("indigo", "#6366f1", "#6366f1"),
    CategoryPreset("purple", "#a855f7", "#a855f7"),
    CategoryPreset("magenta", "#ec4899", "#ec4899"),
)


@dataclass(frozen=True, slots=True)
class CategoryColor:
    """Result for a stored colour: a preset name, or a custom name plus its rule."""

    name: str | None
    cat: str | None
    edge: str | None
    custom: bool

    @property
    def rule(self) -> str:
        """CSS rule for a custom hue (empty for presets and the neutral default)."""
        if not self.custom:
            return ""
        return f'[data-color="{self.name}"]{{--cat:{self.cat};--cat-edge:{self.edge}}}'


def _channels(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _to_hex(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    return f"#{red:02x}{green:02x}{blue:02x}"


def relative_luminance(color: str) -> float:
    """WCAG relative luminance of a ``#rrggbb`` colour."""
    total = 0.0
    for channel, weight in zip(_channels(color), _LUMA_WEIGHTS, strict=True):
        value = channel / _CHANNEL_MAX
        linear = value / 12.92 if value <= _SRGB_LINEAR_CUTOFF else ((value + 0.055) / 1.055) ** 2.4
        total += weight * linear
    return total


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio (1..21) between two ``#rrggbb`` colours."""
    lum_a, lum_b = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def edge_color(color: str, background: str = PANEL_BACKGROUND) -> str:
    """The hue itself when it holds 3:1 on ``background``, else scaled down in 1/128 steps."""
    base = color.lower()
    if contrast_ratio(base, background) >= MIN_EDGE_CONTRAST:
        return base
    red, green, blue = _channels(base)
    for step in range(_SCALE_STEPS - 1, -1, -1):
        scaled = (
            red * step >> _SCALE_BITS,
            green * step >> _SCALE_BITS,
            blue * step >> _SCALE_BITS,
        )
        candidate = _to_hex(scaled)
        if contrast_ratio(candidate, background) >= MIN_EDGE_CONTRAST:
            return candidate
    return "#000000"  # unreachable: black holds >= 3:1 on any light panel


def preset_for(color: str) -> CategoryPreset | None:
    """The preset whose ``--cat`` equals ``color`` (case-insensitive), if any."""
    wanted = color.lower()
    return next((preset for preset in PRESETS if preset.cat == wanted), None)


def category_color(color: str | None) -> CategoryColor:
    """Map a stored 6-digit hex (``categories.color``) to a ``data-color`` choice.

    ``None``/empty -> neutral default (no ``data-color``). Preset hex -> its name.
    Other hex -> ``c-<hex>`` with a computed edge (rendered in a nonce'd rule).
    """
    if not color:
        return CategoryColor(name=None, cat=None, edge=None, custom=False)
    preset = preset_for(color)
    if preset is not None:
        return CategoryColor(name=preset.name, cat=preset.cat, edge=preset.edge, custom=False)
    hue = "#" + color.lstrip("#").lower()
    return CategoryColor(name="c-" + hue[1:], cat=hue, edge=edge_color(hue), custom=True)
