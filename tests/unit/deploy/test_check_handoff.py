"""Executable Definition of Done for a handoff package (T-DW04, ADR-0151 §3-§4)."""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Error, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_handoff", ROOT / "scripts/ci/check_handoff.py"
)
assert _spec is not None and _spec.loader is not None
check_handoff = importlib.util.module_from_spec(_spec)
sys.modules["check_handoff"] = check_handoff
_spec.loader.exec_module(check_handoff)

MANIFEST = """\
name = "demo"
kind = "extension"
base = "base-pkg"
canvas = "https://claude.ai/artifact/abc"
spec = "docs/design/specs/demo.md"
delivered = "2026-11-25"

[[board]]
artboard = "Goals-light.dc.html"
page = "pages/goals.html"
viewport = 1440
theme = "light"

[[board]]
artboard = "Goals-dark.dc.html"
page = "pages/goals.html"
viewport = 1440
theme = "dark"
"""
README = """\
# Demo
## Source
canvas
## What changed
new
## Deviations
none
## Not in this package
nothing
"""
BASE_TOKENS = """\
:root { --color-ground: #fff; --color-ink: #121010; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --color-ground: #0d0d0b; --color-ink: #edede6; }
}
:root[data-theme="dark"] { --color-ground: #0d0d0b; --color-ink: #edede6; }
"""
PAGE = """\
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Goals</title>
<link rel="stylesheet" href="../../base-pkg/static/css/tokens.css">
<link rel="stylesheet" href="../static/css/goals.css">
</head><body>
<a href="../index.html">home</a>
<button type="button" id="open" aria-expanded="false">open</button>
<div id="menu" hidden>menu</div>
<button type="button" data-handoff-inert="decorative">look</button>
<script src="../static/js/goals.js"></script>
</body></html>
"""
GOALS_CSS = """\
@import url("../../../base-pkg/static/css/tokens.css");
body { background: var(--color-ground); color: var(--color-ink); }
.goal { background: var(--color-goal); }
"""
SHELL = """\
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Demo</title>
<link rel="stylesheet" href="{css}"></head><body>{body}</body></html>
"""
INDEX_BODY = '<a href="components.html">c</a> <a href="pages/goals.html">g</a>'
JS = """\
document.getElementById("open").addEventListener("click", (e) => {
  e.currentTarget.setAttribute("aria-expanded", "true");
  document.getElementById("menu").hidden = false;
});
"""


def make_package(tmp: Path, **overrides: str) -> Path:
    base = tmp / "base-pkg" / "static" / "css"
    base.mkdir(parents=True)
    (base / "tokens.css").write_text(BASE_TOKENS)
    pkg = tmp / "demo"
    files = {
        "handoff.toml": MANIFEST,
        "README.md": README,
        "index.html": SHELL.format(css="static/css/goals.css", body=INDEX_BODY),
        "components.html": SHELL.format(
            css="static/css/goals.css", body='<a href="index.html">home</a>'
        ),
        "pages/goals.html": PAGE,
        "static/css/goals.css": GOALS_CSS,
        "static/css/tokens.css": ":root { --color-goal: #ffe9db; }\n",
        "static/js/goals.js": JS,
    } | overrides
    for rel, text in files.items():
        (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
        (pkg / rel).write_text(text)
    return pkg


def lines(findings: list[Any]) -> list[str]:
    return [f.line() for f in findings]


# --- manifest -------------------------------------------------------------------


def test_manifest_problems_are_named() -> None:
    manifest, problems = check_handoff.parse_manifest(
        {"name": "x", "kind": "extension", "canvas": "http://example.com", "board": [{"page": "p"}]}
    )
    assert manifest is None
    assert problems == [
        "missing key spec",
        "missing key delivered",
        "an extension names its base package",
        "canvas must be a claude.ai artifact URL",
        "board 1: missing artboard, viewport, theme",
        "no [[board]] rows",
    ]


def test_manifest_reads_boards_and_deviation_ratios() -> None:
    data = tomllib.loads(
        MANIFEST + '\n[[deviation]]\nid = 1\npage = "pages/goals.html"\nratio = 0.01\n'
    )
    manifest, problems = check_handoff.parse_manifest(data)
    assert problems == []
    assert manifest.kind == "extension"
    assert manifest.base == "base-pkg"
    assert [(b.artboard, b.theme, b.viewport) for b in manifest.boards] == [
        ("Goals-light.dc.html", "light", 1440),
        ("Goals-dark.dc.html", "dark", 1440),
    ]
    assert manifest.ratios == {"pages/goals.html": 0.01}


# --- static checks ----------------------------------------------------------------


def test_theme_copies_fail() -> None:
    finding = check_handoff.check_theme_copies(["pages/a.html", "pages/a.light.html"])
    assert (
        finding.line()
        == "FAIL theme-copies: pages/a.light.html: one markup per page, themes from tokens"
    )


def test_readme_needs_every_section() -> None:
    finding = check_handoff.check_readme("# X\n## Source\n## Deviations (3)\n")
    assert (
        finding.line()
        == "FAIL readme: no '## What changed' section; no '## Not in this package' section"
    )


def test_colour_literals_outside_tokens_are_found_with_lines() -> None:
    css = (
        "/* #abc in a comment */\n.a { color: #fff; }\n"
        ".b { background: rgb(0 0 0 / 10%); }\n#bed { color: var(--color-ink); }\n"
    )
    assert check_handoff.colour_literals("static/css/a.css", css) == [
        "static/css/a.css:2 #fff",
        "static/css/a.css:3 rgb(",
    ]
    assert check_handoff.colour_literals("static/css/tokens.css", css) == []
    html = (
        '<p style="color: #123456">x</p>\n<svg><path fill="#000" d="M0"/></svg>\n<p>#1 in text</p>'
    )
    assert check_handoff.colour_literals("pages/a.html", html) == [
        "pages/a.html:1 #123456",
        "pages/a.html:2 #000",
    ]


def test_extension_may_not_redefine_a_base_token() -> None:
    finding = check_handoff.check_base_tokens(
        ":root { --color-ink: red; --color-new: #fff; }", BASE_TOKENS
    )
    assert finding.line() == "FAIL base-tokens: redefines base token --color-ink"


def test_outside_urls_fail_but_svg_namespaces_do_not() -> None:
    texts = {
        "pages/a.html": '<svg xmlns="http://www.w3.org/2000/svg"></svg><link href="https://fonts.googleapis.com/x">',
        "static/css/a.css": "@import url('//cdn.example.com/x.css');",
    }
    assert check_handoff.check_urls(texts).line() == (
        "FAIL outside-urls: pages/a.html -> https://fonts.googleapis.com/x; "
        "static/css/a.css -> //cdn.example.com/x.css"
    )


def test_links_must_resolve_inside_allowed_roots() -> None:
    texts = {
        "pages/a.html": '<a href="b.html#x">b</a><img src="../../secret.png"><a href="#top">t</a>'
    }
    finding = check_handoff.check_links(
        texts,
        exists=lambda _f, target: target.startswith("../"),
        allowed=lambda _f, target: not target.startswith("../../"),
    )
    assert finding.line() == (
        "FAIL links: pages/a.html -> b.html#x: missing; "
        "pages/a.html -> ../../secret.png: outside the package and its base"
    )


def test_every_page_is_reachable_from_index() -> None:
    texts = {
        "index.html": '<a href="pages/a.html">a</a>',
        "pages/a.html": '<a href="./b.html">b</a>',
        "pages/b.html": "",
        "pages/orphan.html": "",
    }
    assert check_handoff.check_reachable(texts).line() == (
        "FAIL reachable: pages/orphan.html not reachable from index.html"
    )


def test_every_page_needs_a_light_and_a_dark_board() -> None:
    boards = [
        check_handoff.Board("A-light.dc.html", "pages/a.html", 1440, "light"),
        check_handoff.Board("Gone.dc.html", "pages/gone.html", 375, "dark"),
    ]
    finding = check_handoff.check_coverage(["pages/a.html"], boards, lambda p: p == "pages/a.html")
    assert finding.line() == (
        "FAIL coverage: board Gone.dc.html -> pages/gone.html: no such page; "
        "pages/a.html: no dark artboard"
    )


def test_checksums_must_be_current() -> None:
    expected = check_handoff.manifest_lines({"b.txt": b"b", "a.txt": b"a"})
    assert expected.splitlines()[0].endswith("  ./a.txt")
    assert check_handoff.check_checksums(expected, None).level == "FAIL"
    assert check_handoff.check_checksums(expected, expected + "x").line() == (
        "FAIL checksums: manifest is stale: run with --write-manifest"
    )
    assert check_handoff.check_checksums(expected, expected).level == "PASS"


# --- whole package ------------------------------------------------------------------


def test_clean_package_passes_and_writes_its_manifest(tmp_path: Path) -> None:
    pkg = make_package(tmp_path)
    first = lines(check_handoff.run(pkg, render=False, refs=None, write_manifest=False))
    assert first[-1] == "FAIL checksums: no checksum manifest: run with --write-manifest"
    assert [line for line in first[:-1] if not line.startswith("PASS")] == []
    written = lines(check_handoff.run(pkg, render=False, refs=None, write_manifest=True))
    assert written[-1] == "PASS checksums: wrote demo.sha256"
    again = lines(check_handoff.run(pkg, render=False, refs=None, write_manifest=False))
    assert all(line.startswith("PASS") for line in again)
    assert check_handoff.main([str(pkg)]) == 0


def test_package_with_a_colour_literal_fails(tmp_path: Path) -> None:
    pkg = make_package(tmp_path, **{"static/css/goals.css": ".goal { color: #f00; }\n"})
    found = lines(check_handoff.run(pkg, render=False, refs=None, write_manifest=True))
    assert "FAIL colours: static/css/goals.css:1 #f00" in found
    assert not (tmp_path / "demo.sha256").exists()


def test_missing_manifest_fails(tmp_path: Path) -> None:
    assert lines(check_handoff.run(tmp_path, render=False, refs=None, write_manifest=False)) == [
        f"FAIL manifest: no handoff.toml in {tmp_path}"
    ]


def _chromium_available() -> bool:
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Error:
        return False
    return True


@pytest.mark.skipif(not _chromium_available(), reason="Playwright Chromium is not installed")
def test_render_flags_an_unwired_button_and_passes_a_wired_one(tmp_path: Path) -> None:
    inert = '<button type="button" data-handoff-inert'
    dead = PAGE.replace(inert, '<button type="button">dead</button>\n' + inert)
    pkg = make_package(tmp_path, **{"pages/goals.html": dead})
    found = lines(check_handoff.run(pkg, render=True, refs=None, write_manifest=False))
    assert "PASS render: no console error, failed or outside request, or horizontal scroll" in found
    assert "PASS themes: dark differs from light on every page" in found
    assert (
        "FAIL wiring: pages/goals.html: 'dead' does nothing (wire it or mark data-handoff-inert)"
        in found
    )
