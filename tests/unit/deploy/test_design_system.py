"""Repo design system generated from the shipped tokens (T-DW02, ADR-0154 §1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_hspec = importlib.util.spec_from_file_location(
    "check_handoff_ds", ROOT / "scripts/ci/check_handoff.py"
)
assert _hspec is not None and _hspec.loader is not None
check_handoff = importlib.util.module_from_spec(_hspec)
sys.modules["check_handoff_ds"] = check_handoff
_hspec.loader.exec_module(check_handoff)
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
            "value": {
                "light": "0 16px 40px rgb(18 16 16 / 12%)",
                "dark": "0 16px 40px rgb(0 0 0 / 50%)",
            },
            "usage": "`--shadow-menu` in tokens.css.",
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


def test_extra_tokens_keep_only_what_the_system_does_not_carry() -> None:
    css = (
        ":root { --color-ink: #121010; --z-modal: 50; "
        "--ring-now: inset 0 0 0 1px var(--color-ink); }\n"
        ':root[data-theme="dark"] { --color-ink: #edede6; --ring-now: 0 0 0 0 transparent; }\n'
    )
    assert design_system.extra_tokens(css, {"color-ink"}) == (
        ":root {\n"
        "  --z-modal: 50;\n"
        "  --ring-now: inset 0 0 0 1px var(--color-ink);\n"
        "}\n"
        "@media (prefers-color-scheme: dark) {\n"
        '  :root:not([data-theme="light"]) {\n'
        "    --ring-now: 0 0 0 0 transparent;\n"
        "  }\n"
        "}\n"
        ':root[data-theme="dark"] {\n'
        "  --ring-now: 0 0 0 0 transparent;\n"
        "}\n"
    )


def test_bundle_flattens_imports_in_layers_without_page_css_or_font_faces() -> None:
    main_css = (
        "@layer reset, tokens, components, pages;\n"
        '@import url("tokens.css") layer(tokens);\n'
        '@import url("base.css") layer(base);\n'
        '@import url("components/button.css") layer(components);\n'
        '@import url("pages/today.css") layer(pages);\n'
        '@import url("pages/components.css") layer(pages);\n'
    )
    sources = {
        "base.css": '@font-face { font-family: X; src: url("x.woff2"); }\nbody { margin: 0; }',
        "components/button.css": ".rd-btn { color: var(--color-ink); }",
        "pages/components.css": ".rd-comp-card { padding: 0; }",
    }
    css = (
        ":root { --color-ink: #121010; --z-modal: 50; }\n"
        ':root[data-theme="dark"] { --color-ink: #fff; }\n'
    )
    bundle = design_system.bundle_css(main_css, sources.__getitem__, css, {"color-ink"})
    assert "@layer reset, tokens, components, pages;" in bundle
    assert "/* tokens.css */\n@layer tokens {\n:root {\n  --z-modal: 50;\n}\n}" in bundle
    assert "/* base.css */\n@layer base {\nbody { margin: 0; }\n}" in bundle
    assert (
        "/* components/button.css */\n@layer components {\n.rd-btn { color: var(--color-ink); }\n}"
        in bundle
    )
    assert "pages/today.css" not in bundle
    assert "/* pages/components.css */" in bundle
    assert "@font-face" not in bundle


def test_components_come_from_the_board_sections() -> None:
    html = (
        '<svg class="rd-sprite"><symbol id="icon-x"></symbol></svg>'
        '<section class="rd-card rd-comp-card rd-comp-card--span2" aria-label="colour roles">'
        "x</section>"
        '<section class="rd-card rd-comp-card rd-comp-card--span1" aria-label="buttons">'
        '<h2 class="rd-caption">buttons</h2>'
        '<button class="rd-btn rd-btn--primary">[ save ]</button>'
        '<svg class="rd-icon"><use href="#icon-x"/></svg>'
        '<p class="rd-caption">primary · quiet</p></section>'
    )
    files = design_system.components(html)
    assert sorted(files) == ["components/Button/README.md", "components/Button/preview.html"]
    preview = files["components/Button/preview.html"]
    assert preview.splitlines()[0] == (
        '<!-- @dsCard group="Actions" height=240 width=480 subtitle="buttons" -->'
    )
    assert '<symbol id="icon-x">' in preview
    assert '<section class="rd-card rd-comp-card" aria-label="buttons">' in preview
    readme = files["components/Button/README.md"]
    assert "On the base board: primary · quiet." in readme
    assert "Classes (from `components/bundle.css`): `.rd-btn`, `.rd-icon`." in readme


def test_committed_components_use_tokens_only_and_cover_the_board() -> None:
    previews = sorted(design_system.SYSTEM.glob("components/*/preview.html"))
    names = {p.parent.name for p in previews}
    assert names == {c.name for c in design_system.COMPONENTS.values()} | {"Cover"}
    for preview in previews:
        assert check_handoff.colour_literals(preview.name, preview.read_text()) == []
