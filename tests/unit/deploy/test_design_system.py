"""Repo design system generated from the shipped tokens (T-DW02, ADR-0151 §1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("design_system", ROOT / "scripts/design_system.py")
assert _spec is not None and _spec.loader is not None
design_system = importlib.util.module_from_spec(_spec)
sys.modules["design_system"] = design_system
_spec.loader.exec_module(design_system)

CSS = """\
:root {
  --color-ground: #fff;
  --color-ink: #121010;
  --cat-default: var(--color-ink);
  --shadow-menu: 0 16px 40px rgb(18 16 16 / 12%);
  --font-display: "Unbounded", system-ui, sans-serif;
  --font-mono: "Geist Mono", monospace;
  --font-size-mega: 80px;       /* Today phone figure */
  --font-size-heading: 14px;
  --line-height-mega: 0.9;
  --letter-spacing-mega: -0.05em;
  --line-height-heading: 20px;
  --space-0: 0;
  --space-4: 16px;
  --space-palette-top: 12vh;
  --radius-lg: 28px;
  --size-control: 44px;         /* every touch target */
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --color-ground: #111; }
}
:root[data-theme="dark"] {
  --color-ground: #0d0d0b;
  --color-ink: #edede6;
  --shadow-menu: 0 16px 40px rgb(0 0 0 / 50%);
}
"""


def test_tokens_follow_the_css_with_both_themes() -> None:
    tokens = design_system.build(CSS, {"color-ink": "Text on ground."})
    assert tokens["color"]["themes"] == [
        {"id": "light", "name": "Light"},
        {"id": "dark", "name": "Dark"},
    ]
    assert tokens["color"]["tokens"] == [
        {
            "name": "color-ground",
            "value": {"light": "#fff", "dark": "#0d0d0b"},
            "usage": "`--color-ground` in tokens.css.",
        },
        {
            "name": "color-ink",
            "value": {"light": "#121010", "dark": "#edede6"},
            "usage": "Text on ground.",
        },
    ]
    assert tokens["spacing"]["tokens"] == [
        {"name": "space-0", "value": "0px", "usage": "`--space-0` in tokens.css."},
        {"name": "space-4", "value": "16px", "usage": "`--space-4` in tokens.css."},
    ]
    assert tokens["size"]["tokens"] == [
        {"name": "size-control", "value": "44px", "usage": "every touch target"}
    ]
    assert tokens["shadow"]["tokens"] == [
        {
            "name": "shadow-menu",
            "value": "0 16px 40px rgb(18 16 16 / 12%)",
            "usage": "`--shadow-menu` in tokens.css. Dark: `0 16px 40px rgb(0 0 0 / 50%)`.",
        }
    ]


def test_type_styles_pair_sizes_with_line_heights_and_fonts() -> None:
    tokens = design_system.build(CSS, {})
    display, mono = tokens["type"]["groups"]
    assert display["styles"] == [
        {
            "name": "mega",
            "fontSize": "80px",
            "fontWeight": 700,
            "lineHeight": "0.9",
            "letterSpacing": "-0.05em",
            "usage": "Today phone figure",
        }
    ]
    assert mono["styles"] == [
        {
            "name": "heading",
            "fontSize": "14px",
            "fontWeight": 500,
            "lineHeight": "20px",
            "usage": "`--font-size-heading` in tokens.css.",
        }
    ]
    assert tokens["type"]["families"] == {
        "display": '"Unbounded", system-ui, sans-serif',
        "mono": '"Geist Mono", monospace',
    }


def test_committed_tokens_json_matches_the_shipped_css() -> None:
    assert design_system.main(["--check"]) == 0
    committed = json.loads(design_system.TOKENS_JSON.read_text())
    names = [t["name"] for t in committed["color"]["tokens"]]
    assert "color-now-fill" in names
    assert all(
        t["usage"] and "in tokens.css" not in t["usage"] for t in committed["color"]["tokens"]
    )
    for font in committed["type"]["fonts"]:
        assert (design_system.BASE / "static" / font["file"]).is_file()
