"""Generate the repo design system's ``tokens.json`` from the shipped tokens (ADR-0154 §1, T-DW02).

Source: the base handoff's ``static/css/tokens.css`` (light in ``:root``, dark in
``:root[data-theme="dark"]``), which the app copies. Output: ``tokens.json`` in the
claude.ai Design System shape (families of ``{"name", "value", "usage"}`` lists,
colours with a light and a dark value). Token names are the CSS custom property
names without ``--``, so a value on a canvas is found in CSS by name.

Usage notes come from ``usage.toml`` next to the output, else from the token's
trailing CSS comment, else a pointer to the property.

Components (ADR-0154 §1): ``components/bundle.css`` is the base package's component
CSS (its ``main.css`` imports in layer order, the page CSS left out except the
components board) plus the base tokens the design system does not carry; one
``components/<Name>/preview.html`` and ``README.md`` per section of the base
``components.html``. The cover (``components/Cover``) is hand-written.

Usage: design_system.py [--check]   (--check: exit 1 when a generated file is stale)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
BASE: Final = ROOT / "docs" / "design" / "rising-dough-frontend"
TOKENS_CSS: Final = BASE / "static" / "css" / "tokens.css"
SYSTEM: Final = ROOT / "docs" / "design" / "system" / "project"
TOKENS_JSON: Final = SYSTEM / "tokens.json"
USAGE_TOML: Final = SYSTEM.parent / "usage.toml"
COMPONENTS_HTML: Final = BASE / "components.html"
MAIN_CSS: Final = BASE / "static" / "css" / "main.css"
BUNDLE_CSS: Final = SYSTEM / "components" / "bundle.css"

NAME: Final = "Rising Dough Sourdough"
THEMES: Final = ({"id": "light", "name": "Light"}, {"id": "dark", "name": "Dark"})
# Unbounded 700 sizes; every other font-size token is Geist Mono.
DISPLAY_SIZES: Final = frozenset(
    {
        "hero-xl",
        "hero-plan",
        "hero-lg",
        "mega",
        "hero-md",
        "hero-sm",
        "dialog-hero",
        "display",
        "display-sm",
        "auth-headline-sm",
        "auth-title",
        "error-title",
        "title",
        "title-sm",
        "brand-sm",
    }
)
MEDIUM_MONO: Final = frozenset({"heading"})
FONTS: Final = (
    {"family": "Unbounded", "file": "fonts/unbounded-700-latin.woff2", "weight": "700"},
    {"family": "Unbounded", "file": "fonts/unbounded-700-latin-ext.woff2", "weight": "700"},
    {"family": "Geist Mono", "file": "fonts/geist-mono-var.woff2", "weight": "400 500"},
)
_LENGTH: Final = re.compile(r"^-?\d+(\.\d+)?(px|rem|em|%)?$")
_IMPORT: Final = re.compile(r'@import url\("([^"]+)"\) layer\(([a-z]+)\);')
_LAYERS: Final = re.compile(r"^@layer [^;{]+;", re.MULTILINE)
_FONT_FACE: Final = re.compile(r"@font-face\s*\{[^}]*\}\s*")
_SECTION: Final = re.compile(
    r'<section class="rd-card rd-comp-card rd-comp-card--span(\d)" aria-label="([^"]+)">'
    r"(.*?)</section>",
    re.DOTALL,
)
_SPRITE: Final = re.compile(r'<svg class="rd-sprite".*?</svg>', re.DOTALL)
_BLOCK_CLASS: Final = re.compile(r'class="([^"]+)"')
_CAPTION: Final = re.compile(r'<p class="rd-caption">([^<]+)</p>\s*$')


@dataclass(frozen=True)
class Component:
    name: str
    group: str
    summary: str


# components.html section label -> design system component. "colour roles" and
# "type" are left out: the Colors and Typography views show them from tokens.json.
COMPONENTS: Final = {
    "amounts": Component(
        "Amount",
        "Data",
        "Money amounts: Geist Mono figures, currency in muted ink, real minus sign.",
    ),
    "chips · status": Component(
        "Chip", "Data", "Category chips in the category palette, and status tags."
    ),
    "buttons": Component(
        "Button",
        "Actions",
        "Buttons: primary (now-fill, bracketed, one per surface), secondary, quiet, "
        "destructive, disabled.",
    ),
    "segmented · tabs": Component(
        "Segmented",
        "Actions",
        "Segmented control for ranges, tabs and on/off choices; the selected option is ink.",
    ),
    "bars · loaves": Component(
        "Bar",
        "Data",
        "Block-cell progress bars and loaf charts: past loaves in past, this period in now-fill.",
    ),
    "year cells": Component(
        "YearCell", "Data", "Year-grid cells: default, recurring override, one-off override, unset."
    ),
    "toast · menu · flash": Component(
        "Toast", "Feedback", "Toast with undo, row menu and flash messages."
    ),
    "fields · category picker": Component(
        "Field", "Forms", "Text fields, amount input and the category picker."
    ),
    "navigation": Component(
        "Navigation", "Navigation", "Phone tab bar and desktop main navigation."
    ),
    "dialog headers": Component(
        "DialogHeader",
        "Overlays",
        "Dialog headers: bake band with hero value, slim band with action, confirm without band.",
    ),
    "empty · loading": Component("EmptyState", "Feedback", "Empty and loading states."),
}
# Board chrome and text helpers every section uses; not part of a component.
_CHROME_CLASSES: Final = frozenset({"rd-card", "rd-caption", "rd-muted", "rd-body"})
_PREVIEW_WIDTH: Final = {"1": 480, "2": 720, "3": 960}
_PREVIEW_HEIGHT: Final = {"1": 240, "2": 280, "3": 360}

_DECL: Final = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);[ \t]*(?:/\*\s*(.*?)\s*\*/)?")


@dataclass(frozen=True)
class Decl:
    name: str
    value: str
    comment: str


def block(css: str, selector: str) -> str:
    """Body of the first top-level rule whose selector is exactly ``selector``."""
    start = css.find(selector + " {")
    if start < 0:
        raise ValueError(f"selector not found: {selector}")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return css[i + 1 : j]
    raise ValueError(f"unclosed rule: {selector}")


def declarations(body: str) -> dict[str, Decl]:
    found: dict[str, Decl] = {}
    for m in _DECL.finditer(body):
        found[m.group(1)] = Decl(m.group(1), m.group(2).strip(), m.group(3) or "")
    return found


def _usage(name: str, decl: Decl, usage: Mapping[str, str]) -> str:
    return usage.get(name) or decl.comment or f"`--{name}` in tokens.css."


def _is_literal(value: str) -> bool:
    return "var(" not in value and "color-mix(" not in value


def _length(value: str) -> str | None:
    if value == "0":
        return "0px"
    return value if _LENGTH.match(value) else None


def colour_tokens(
    light: Mapping[str, Decl], dark: Mapping[str, Decl], usage: Mapping[str, str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, decl in light.items():
        if not name.startswith("color-") or not _is_literal(decl.value):
            continue
        dark_value = dark[name].value if name in dark else decl.value
        out.append(
            {
                "name": name,
                "value": {"light": decl.value, "dark": dark_value},
                "usage": _usage(name, decl, usage),
            }
        )
    return out


def length_tokens(
    light: Mapping[str, Decl], prefix: str, usage: Mapping[str, str]
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name, decl in light.items():
        value = _length(decl.value)
        if name.startswith(prefix) and value is not None:
            out.append({"name": name, "value": value, "usage": _usage(name, decl, usage)})
    return out


def shadow_tokens(
    light: Mapping[str, Decl], dark: Mapping[str, Decl], usage: Mapping[str, str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, decl in light.items():
        if name.startswith("shadow-"):
            dark_value = dark[name].value if name in dark else decl.value
            value = {"light": decl.value, "dark": dark_value}
            out.append({"name": name, "value": value, "usage": _usage(name, decl, usage)})
    return out


def type_styles(light: Mapping[str, Decl], usage: Mapping[str, str]) -> list[dict[str, Any]]:
    display: list[dict[str, Any]] = []
    mono: list[dict[str, Any]] = []
    for name, decl in light.items():
        if not name.startswith("font-size-"):
            continue
        style = name.removeprefix("font-size-")
        is_display = style in DISPLAY_SIZES
        weight = 700 if is_display else 500 if style in MEDIUM_MONO else 400
        entry: dict[str, Any] = {"name": style, "fontSize": decl.value, "fontWeight": weight}
        if f"line-height-{style}" in light:
            entry["lineHeight"] = light[f"line-height-{style}"].value
        if f"letter-spacing-{style}" in light:
            entry["letterSpacing"] = light[f"letter-spacing-{style}"].value
        entry["usage"] = _usage(name, decl, usage)
        (display if is_display else mono).append(entry)
    return [
        {"name": "Unbounded", "family": "display", "styles": display},
        {"name": "Geist Mono", "family": "mono", "styles": mono},
    ]


def build(css: str, usage: Mapping[str, str]) -> dict[str, Any]:
    light = declarations(block(css, ":root"))
    dark = declarations(block(css, ':root[data-theme="dark"]'))
    return {
        "name": NAME,
        "version": 1,
        "meta": {"source": "docs/design/rising-dough-frontend/static/css/tokens.css"},
        "color": {"themes": list(THEMES), "tokens": colour_tokens(light, dark, usage)},
        "type": {
            "fonts": list(FONTS),
            "families": {"display": light["font-display"].value, "mono": light["font-mono"].value},
            "groups": type_styles(light, usage),
        },
        "spacing": {"tokens": length_tokens(light, "space-", usage)},
        "radius": {"tokens": length_tokens(light, "radius-", usage)},
        "size": {"tokens": length_tokens(light, "size-", usage)},
        "shadow": {"tokens": shadow_tokens(light, dark, usage)},
    }


def token_names(tokens: Mapping[str, Any]) -> set[str]:
    """Custom properties the design system's generated tokens.css defines."""
    names = {f"font-{key}" for key in tokens["type"]["families"]}
    for family, body in tokens.items():
        if isinstance(body, dict) and "tokens" in body and family != "type":
            names |= {t["name"] for t in body["tokens"]}
    return names


def extra_tokens(css: str, carried: set[str]) -> str:
    """Base tokens the design system does not carry, light in :root, dark overrides."""
    light = declarations(block(css, ":root"))
    dark = declarations(block(css, ':root[data-theme="dark"]'))
    keep = [d for n, d in light.items() if n not in carried]
    dark_keep = [d for n, d in dark.items() if n not in carried and n in light]
    lines = [":root {", *(f"  --{d.name}: {d.value};" for d in keep), "}"]
    if dark_keep:
        body = [f"    --{d.name}: {d.value};" for d in dark_keep]
        lines += [
            "@media (prefers-color-scheme: dark) {",
            '  :root:not([data-theme="light"]) {',
            *body,
            "  }",
            "}",
            ':root[data-theme="dark"] {',
            *(line.removeprefix("  ") for line in body),
            "}",
        ]
    return "\n".join(lines) + "\n"


def bundle_css(
    main_css: str, read: Callable[[str], str], tokens_css: str, carried: set[str]
) -> str:
    """main.css flattened: tokens replaced by the extras, page CSS dropped but the board's."""
    layers = _LAYERS.search(main_css)
    out = [
        "/* Rising Dough — Sourdough: component CSS, generated by scripts/design_system.py from",
        " * docs/design/rising-dough-frontend/static/css/main.css. Do not edit. */",
        layers.group() if layers else "",
    ]
    for path, layer in _IMPORT.findall(main_css):
        if path == "tokens.css":
            text = extra_tokens(tokens_css, carried)
        elif path.startswith("pages/") and path != "pages/components.css":
            continue
        else:
            text = _FONT_FACE.sub("", read(path))
        out.append(f"/* {path} */\n@layer {layer} {{\n{text.strip()}\n}}")
    return "\n\n".join(part for part in out if part) + "\n"


def _blocks(markup: str) -> list[str]:
    """Component block classes in first-use order (no elements, modifiers or board chrome)."""
    seen: list[str] = []
    for classes in _BLOCK_CLASS.findall(markup):
        for cls in classes.split():
            block_class = cls.startswith("rd-") and "__" not in cls and "--" not in cls
            board = cls.startswith("rd-comp") or cls in _CHROME_CLASSES
            if block_class and not board and cls not in seen:
                seen.append(cls)
    return seen


def components(html: str) -> dict[str, str]:
    """``components/<Name>/preview.html`` and ``README.md`` per base components.html section."""
    sprite_match = _SPRITE.search(html)
    sprite = sprite_match.group() if sprite_match else ""
    files: dict[str, str] = {}
    for span, label, body in _SECTION.findall(html):
        comp = COMPONENTS.get(label)
        if comp is None:
            continue
        section = f'<section class="rd-card rd-comp-card" aria-label="{label}">{body}</section>'
        needs_sprite = "#icon-" in body
        files[f"components/{comp.name}/preview.html"] = "\n".join(
            [
                f'<!-- @dsCard group="{comp.group}" height={_PREVIEW_HEIGHT[span]} '
                f'width={_PREVIEW_WIDTH[span]} subtitle="{label}" -->',
                "<!doctype html>",
                '<html lang="en">',
                '<head><meta charset="utf-8"><title>' + comp.name + "</title></head>",
                '<body class="rd-app rd-app--bare">',
                *([sprite] if needs_sprite else []),
                section,
                "</body>",
                "</html>",
                "",
            ]
        )
        caption = _CAPTION.search(body.strip())
        notes = f"\n\nOn the base board: {caption.group(1).strip()}." if caption else ""
        classes = ", ".join(f"`.{c}`" for c in _blocks(body))
        files[f"components/{comp.name}/README.md"] = (
            f"# {comp.name}\n\n{comp.summary}{notes}\n\n"
            f"Classes (from `components/bundle.css`): {classes}.\n\n"
            f"Source: the *{label}* section of the base package's `components.html`; "
            "the markup in the preview is the markup the app ships. Use the classes, "
            "never restyle them with literal values; both themes come from the tokens.\n"
        )
    return files


def generated(usage: Mapping[str, str]) -> dict[Path, str]:
    """Every generated file of the design system, by path."""
    css = TOKENS_CSS.read_text()
    tokens = build(css, usage)
    css_dir = MAIN_CSS.parent
    out = {
        TOKENS_JSON: render(tokens),
        BUNDLE_CSS: bundle_css(
            MAIN_CSS.read_text(), lambda p: (css_dir / p).read_text(), css, token_names(tokens)
        ),
    }
    for rel, text in components(COMPONENTS_HTML.read_text()).items():
        out[SYSTEM / rel] = text
    return out


def render(tokens: Mapping[str, Any]) -> str:
    return json.dumps(tokens, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when a generated file is stale")
    args = parser.parse_args(argv)
    usage = tomllib.loads(USAGE_TOML.read_text()) if USAGE_TOML.exists() else {}
    files = generated(usage)
    if args.check:
        stale = [p for p, text in files.items() if not p.exists() or p.read_text() != text]
        for p in stale:
            print(f"FAIL {p.relative_to(ROOT)} is stale: run just design-system")
        if not stale:
            print(f"PASS {len(files)} generated design-system files match the base package")
        return 1 if stale else 0
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(f"wrote {len(files)} files under {SYSTEM.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
