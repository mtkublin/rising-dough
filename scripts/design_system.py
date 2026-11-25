"""Generate the repo design system's ``tokens.json`` from the shipped tokens (ADR-0151 §1, T-DW02).

Source: the base handoff's ``static/css/tokens.css`` (light in ``:root``, dark in
``:root[data-theme="dark"]``), which the app copies. Output: ``tokens.json`` in the
claude.ai Design System shape (families of ``{"name", "value", "usage"}`` lists,
colours with a light and a dark value). Token names are the CSS custom property
names without ``--``, so a value on a canvas is found in CSS by name.

Usage notes come from ``usage.toml`` next to the output, else from the token's
trailing CSS comment, else a pointer to the property.

Usage: design_system.py [--check]   (--check: exit 1 when the committed file is stale)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
BASE: Final = ROOT / "docs" / "design" / "rising-dough-frontend"
TOKENS_CSS: Final = BASE / "static" / "css" / "tokens.css"
SYSTEM: Final = ROOT / "docs" / "design" / "system" / "project"
TOKENS_JSON: Final = SYSTEM / "tokens.json"
USAGE_TOML: Final = SYSTEM.parent / "usage.toml"

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
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name, decl in light.items():
        if name.startswith("shadow-"):
            note = _usage(name, decl, usage)
            dark_note = f" Dark: `{dark[name].value}`." if name in dark else ""
            out.append({"name": name, "value": decl.value, "usage": note + dark_note})
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


def render(tokens: Mapping[str, Any]) -> str:
    return json.dumps(tokens, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when tokens.json is stale")
    args = parser.parse_args(argv)
    usage = tomllib.loads(USAGE_TOML.read_text()) if USAGE_TOML.exists() else {}
    text = render(build(TOKENS_CSS.read_text(), usage))
    if args.check:
        if not TOKENS_JSON.exists() or TOKENS_JSON.read_text() != text:
            print(f"FAIL {TOKENS_JSON.relative_to(ROOT)} is stale: run just design-system")
            return 1
        print(f"PASS {TOKENS_JSON.relative_to(ROOT)} matches tokens.css")
        return 0
    TOKENS_JSON.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_JSON.write_text(text)
    print(f"wrote {TOKENS_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
