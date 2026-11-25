"""Executable Definition of Done for one handoff package (ADR-0151 §3-§4, T-DW04).

Checks a package under ``docs/design/<name>/`` against ``docs/design/handoff-template.md``.

Static (always): manifest, layout, README sections, no theme copies, colours from
tokens only, no base-token redefinition, no outside URLs, every relative link
resolves, every page reachable from ``index.html``, every page covered by a light
and a dark ``[[board]]`` row, checksum manifest current.
``--render``: every page in light and dark at its board viewports opens with no
console error, failed request, outside request or horizontal scroll; dark differs
from light; every visible control is wired (a click navigates, changes the hash or
changes the DOM; ``data-handoff-inert`` exempts).
``--parity <refs>``: each board's page against ``<refs>/<artboard stem>.png``.
``--write-manifest``: (re)write ``docs/design/<name>.sha256`` after the checks pass.

Output: one ``PASS|FAIL|WARN <check>: <detail>`` line per finding. Exit 1 on any FAIL.

Usage: check_handoff.py <dir> [--render] [--parity <refs-dir>] [--write-manifest]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final, Literal, cast
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Error as PlaywrightError, sync_playwright

ROOT: Final = Path(__file__).resolve().parents[2]
KINDS: Final = ("base", "extension")
THEMES: Final = ("light", "dark")
REQUIRED_KEYS: Final = ("name", "kind", "canvas", "spec", "delivered")
BOARD_KEYS: Final = ("artboard", "page", "viewport", "theme")
LAYOUT: Final = ("README.md", "index.html", "components.html", "pages")
README_SECTIONS: Final = ("Source", "What changed", "Deviations", "Not in this package")
PARITY_RATIO: Final = 0.001  # ADR-0147 §2 page-wide limit; cluster cap: T-DW08
VIEWPORT_HEIGHT: Final = 900
MAX_SHOWN: Final = 20  # problems printed per check
TEXT_SUFFIXES: Final = (".html", ".css", ".js", ".svg")
_COLOUR: Final = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(", re.IGNORECASE
)
_STYLE_ATTR: Final = re.compile(r"""\sstyle\s*=\s*("[^"]*"|'[^']*')""", re.IGNORECASE)
_STYLE_BLOCK: Final = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_PAINT_ATTR: Final = re.compile(
    r"""\s(?:fill|stroke|stop-color|flood-color|lighting-color|color)\s*=\s*("[^"]*"|'[^']*')""",
    re.IGNORECASE,
)
_CSS_URL: Final = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)|@import\s+(['"])([^'"]+)\3""")
_CUSTOM_PROP: Final = re.compile(r"(--[a-z0-9-]+)\s*:", re.IGNORECASE)
_CSS_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_VALUE: Final = re.compile(r"[a-z-]+\s*:\s*([^;{}]+)", re.IGNORECASE)
_HEADING: Final = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_LINK_ATTRS: Final = {"href", "src", "srcset", "poster", "data", "action"}


@dataclass(frozen=True)
class Finding:
    level: str  # PASS, FAIL or WARN
    check: str
    detail: str = ""

    def line(self) -> str:
        return f"{self.level} {self.check}" + (f": {self.detail}" if self.detail else "")


def _verdict(check: str, problems: Sequence[str], ok: str) -> Finding:
    if problems:
        extra = len(problems) - MAX_SHOWN
        shown = "; ".join(problems[:MAX_SHOWN]) + (f"; +{extra} more" if extra > 0 else "")
        return Finding("FAIL", check, shown)
    return Finding("PASS", check, ok)


# --- manifest -----------------------------------------------------------------


@dataclass(frozen=True)
class Board:
    artboard: str
    page: str
    viewport: int
    theme: str


@dataclass(frozen=True)
class Manifest:
    name: str
    kind: str
    base: str | None
    boards: tuple[Board, ...]
    ratios: Mapping[str, float] = field(default_factory=dict)  # page -> deviation tolerance


def parse_manifest(data: Mapping[str, Any]) -> tuple[Manifest | None, list[str]]:
    problems = [f"missing key {k}" for k in REQUIRED_KEYS if k not in data]
    kind = data.get("kind")
    if kind not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    base = data.get("base")
    if kind == "extension" and not base:
        problems.append("an extension names its base package")
    if not str(data.get("canvas", "")).startswith("https://claude.ai/"):
        problems.append("canvas must be a claude.ai artifact URL")
    boards: list[Board] = []
    for i, row in enumerate(data.get("board", [])):
        missing = [k for k in BOARD_KEYS if k not in row]
        if missing:
            problems.append(f"board {i + 1}: missing {', '.join(missing)}")
            continue
        if row["theme"] not in THEMES:
            problems.append(f"board {i + 1}: theme must be light or dark")
        if not isinstance(row["viewport"], int) or row["viewport"] <= 0:
            problems.append(f"board {i + 1}: viewport must be a positive width in px")
        boards.append(
            Board(str(row["artboard"]), str(row["page"]), int(row["viewport"]), str(row["theme"]))
        )
    if not boards:
        problems.append("no [[board]] rows")
    ratios = {
        str(d["page"]): float(d["ratio"])
        for d in data.get("deviation", [])
        if "ratio" in d and "page" in d
    }
    if problems:
        return None, problems
    return Manifest(
        str(data["name"]), str(kind), str(base) if base else None, tuple(boards), ratios
    ), []


# --- static checks ------------------------------------------------------------


def check_layout(present: Iterable[str]) -> Finding:
    have = set(present)
    return _verdict(
        "layout",
        [f"missing {p}" for p in LAYOUT if p not in have],
        "README, index, components, pages",
    )


def check_theme_copies(files: Iterable[str]) -> Finding:
    copies = [f for f in files if f.endswith((".light.html", ".dark.html"))]
    return _verdict(
        "theme-copies",
        [f"{f}: one markup per page, themes from tokens" for f in copies],
        "one markup per page",
    )


def check_readme(text: str) -> Finding:
    headings = [h.lower() for h in _HEADING.findall(text)]
    missing = [s for s in README_SECTIONS if not any(h.startswith(s.lower()) for h in headings)]
    return _verdict("readme", [f"no '## {s}' section" for s in missing], "all sections present")


def _blank(m: re.Match[str]) -> str:
    """Same-length blanks for a comment, so offsets and line numbers stay put."""
    return re.sub(r"[^\n]", " ", m.group())


def colour_literals(path: str, text: str) -> list[str]:
    """Colour literals outside a tokens.css.

    Scans CSS files, inline styles, ``<style>`` blocks and SVG paint attributes.
    """
    if path.endswith("tokens.css"):
        return []
    if path.endswith(".css"):
        # Declaration values only, so an id selector such as #bed is not a colour.
        values = list(_CSS_VALUE.finditer(_CSS_COMMENT.sub(_blank, text)))
        chunks = [m.group(1) for m in values]
        offsets = [m.start(1) for m in values]
    elif path.endswith((".html", ".svg")):
        found = [
            *_STYLE_ATTR.finditer(text),
            *_STYLE_BLOCK.finditer(text),
            *_PAINT_ATTR.finditer(text),
        ]
        chunks = [m.group(1) for m in found]
        offsets = [m.start(1) for m in found]
    else:
        return []
    hits: list[str] = []
    for chunk, offset in zip(chunks, offsets, strict=True):
        for m in _COLOUR.finditer(chunk):
            line = text.count("\n", 0, offset + m.start()) + 1
            hits.append(f"{path}:{line} {m.group()}")
    return sorted(set(hits), key=lambda h: (h.split(":")[0], int(h.split(":")[1].split()[0])))


def check_colours(texts: Mapping[str, str]) -> Finding:
    hits = [h for path, text in sorted(texts.items()) for h in colour_literals(path, text)]
    return _verdict("colours", hits, "colours from tokens only")


def custom_properties(css: str) -> set[str]:
    return set(_CUSTOM_PROP.findall(_CSS_COMMENT.sub("", css)))


def check_base_tokens(extension_tokens: str | None, base_tokens: str | None) -> Finding:
    if extension_tokens is None or base_tokens is None:
        return Finding("PASS", "base-tokens", "no extension tokens.css")
    clash = sorted(custom_properties(extension_tokens) & custom_properties(base_tokens))
    return _verdict(
        "base-tokens", [f"redefines base token {p}" for p in clash], "no base token redefined"
    )


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str, str]] = []  # (tag, attr, value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in _LINK_ATTRS or not value:
                continue
            if name == "srcset":
                self.refs.extend(
                    (tag, name, part.strip().split(" ")[0]) for part in value.split(",")
                )
            elif tag == "object" or name != "data":
                self.refs.append((tag, name, value))


def references(path: str, text: str) -> list[tuple[str, str]]:
    """(kind, url) pairs a file points at; kind is the tag name or ``css``."""
    if path.endswith(".css"):
        refs = []
        for m in _CSS_URL.finditer(_CSS_COMMENT.sub("", text)):
            refs.append(("css", m.group(2) or m.group(4)))
        return refs
    if path.endswith((".html", ".svg")):
        parser = _Links()
        parser.feed(text)
        css_refs = [
            ("css", u)
            for block in _STYLE_BLOCK.findall(text)
            for _, u in references("x.css", block)
        ]
        return [(tag, value) for tag, _, value in parser.refs] + css_refs
    return []


def is_outside(url: str) -> bool:
    parts = urlsplit(url)
    return bool(parts.scheme in ("http", "https") or url.startswith("//"))


def _local_target(url: str) -> str | None:
    """Path part of a relative URL, or None for anchors, data: and other non-file URLs."""
    parts = urlsplit(url)
    if parts.scheme or url.startswith("//") or not parts.path:
        return None
    return unquote(parts.path)


def check_urls(texts: Mapping[str, str]) -> Finding:
    hits = [
        f"{path} -> {url}"
        for path, text in sorted(texts.items())
        for _, url in references(path, text)
        if is_outside(url)
    ]
    return _verdict("outside-urls", hits, "no request outside the package")


def check_links(
    texts: Mapping[str, str],
    exists: Callable[[str, str], bool],
    allowed: Callable[[str, str], bool],
) -> Finding:
    """Every relative reference resolves (``exists(from, url)``) inside an allowed root."""
    problems: list[str] = []
    for path, text in sorted(texts.items()):
        for _, url in references(path, text):
            target = _local_target(url)
            if target is None:
                continue
            if not allowed(path, target):
                problems.append(f"{path} -> {url}: outside the package and its base")
            elif not exists(path, target):
                problems.append(f"{path} -> {url}: missing")
    return _verdict("links", problems, "every relative link resolves")


def _resolve(from_path: str, target: str) -> str:
    parts: list[str] = [] if target.startswith("/") else from_path.split("/")[:-1]
    for seg in target.lstrip("/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            else:
                return "../" + target
        else:
            parts.append(seg)
    return "/".join(parts)


def check_reachable(texts: Mapping[str, str]) -> Finding:
    pages = {p for p in texts if p.endswith(".html")}
    seen, todo = {"index.html"}, ["index.html"]
    while todo:
        current = todo.pop()
        for tag, url in references(current, texts.get(current, "")):
            target = _local_target(url)
            if tag != "a" or target is None:
                continue
            nxt = _resolve(current, target)
            if nxt in pages and nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    orphans = sorted(pages - seen)
    return _verdict(
        "reachable", [f"{p} not reachable from index.html" for p in orphans], f"{len(pages)} pages"
    )


def check_coverage(
    pages: Iterable[str], boards: Sequence[Board], exists: Callable[[str], bool]
) -> Finding:
    problems = [
        f"board {b.artboard} -> {b.page}: no such page" for b in boards if not exists(b.page)
    ]
    themes: dict[str, set[str]] = {}
    for b in boards:
        themes.setdefault(b.page, set()).add(b.theme)
    for page in sorted(pages):
        missing = [t for t in THEMES if t not in themes.get(page, set())]
        if missing:
            problems.append(f"{page}: no {' or '.join(missing)} artboard")
    return _verdict("coverage", problems, f"{len(boards)} boards, light and dark per page")


def manifest_lines(files: Mapping[str, bytes]) -> str:
    return "".join(f"{hashlib.sha256(files[p]).hexdigest()}  ./{p}\n" for p in sorted(files))


def check_checksums(expected: str, recorded: str | None) -> Finding:
    if recorded is None:
        return Finding("FAIL", "checksums", "no checksum manifest: run with --write-manifest")
    if recorded != expected:
        return Finding("FAIL", "checksums", "manifest is stale: run with --write-manifest")
    return Finding("PASS", "checksums", "manifest current")


# --- package I/O ---------------------------------------------------------------


@dataclass(frozen=True)
class Package:
    root: Path
    files: Mapping[str, bytes]
    base_root: Path | None

    @property
    def texts(self) -> dict[str, str]:
        return {
            p: b.decode("utf-8", "replace")
            for p, b in self.files.items()
            if p.endswith(TEXT_SUFFIXES)
        }

    @property
    def pages(self) -> list[str]:
        return sorted(p for p in self.files if p.startswith("pages/") and p.endswith(".html"))

    def html(self) -> list[str]:
        return sorted(p for p in self.files if p.endswith(".html"))


def load(root: Path, base: str | None) -> Package:
    files = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != ".DS_Store"
    }
    return Package(root, files, (root.parent / base).resolve() if base else None)


def _exists_in(pkg: Package) -> Callable[[str, str], bool]:
    def exists(from_path: str, target: str) -> bool:
        return (pkg.root / from_path).parent.joinpath(target).resolve().is_file()

    return exists


def _allowed_in(pkg: Package) -> Callable[[str, str], bool]:
    roots = [pkg.root.resolve()] + ([pkg.base_root / "static"] if pkg.base_root else [])

    def allowed(from_path: str, target: str) -> bool:
        resolved = (pkg.root / from_path).parent.joinpath(target).resolve()
        return any(resolved.is_relative_to(r) for r in roots)

    return allowed


def static_checks(pkg: Package, manifest: Manifest, recorded: str | None) -> list[Finding]:
    texts = pkg.texts
    top = {p.split("/")[0] for p in pkg.files}
    ext_tokens = texts.get("static/css/tokens.css") if manifest.kind == "extension" else None
    base_tokens_path = pkg.base_root / "static" / "css" / "tokens.css" if pkg.base_root else None
    base_tokens = (
        base_tokens_path.read_text() if base_tokens_path and base_tokens_path.is_file() else None
    )
    findings = [
        check_layout(top),
        check_theme_copies(pkg.files),
        check_readme(texts.get("README.md", pkg.files.get("README.md", b"").decode())),
        check_colours(texts),
        check_base_tokens(ext_tokens, base_tokens),
        check_urls(texts),
        check_links(texts, _exists_in(pkg), _allowed_in(pkg)),
        check_reachable(texts),
        check_coverage(pkg.pages, manifest.boards, lambda p: p in pkg.files),
    ]
    if manifest.kind == "extension" and (pkg.base_root is None or not pkg.base_root.is_dir()):
        findings.append(
            Finding("FAIL", "base", f"base package {manifest.base} not found next to the package")
        )
    findings.append(check_checksums(manifest_lines(pkg.files), recorded))
    return findings


# --- render checks (Playwright) -------------------------------------------------

_WIRED_SELECTOR: Final = (
    "button, [role=button], [role=tab], [role=menuitem], [role=menuitemradio], [role=switch], "
    "[role=option], summary, a[href^='#'], input[type=checkbox], input[type=radio]"
)
_CONTROLS_JS: Final = """
sel => Array.from(document.querySelectorAll(sel)).map((el, i) => {
  const r = el.getBoundingClientRect();
  const onPage = r.right > 0 && r.bottom > 0;  // skip links parked off-screen until focused
  const visible = r.width > 0 && r.height > 0 && onPage
    && getComputedStyle(el).visibility !== 'hidden';
  const box = el.matches('input[type=checkbox], input[type=radio]');
  const inert = !!el.closest('[data-handoff-inert]') || el.disabled
    || el.getAttribute('aria-disabled') === 'true';
  const label = el.getAttribute('aria-label') || el.textContent || el.id || el.tagName;
  const name = label.trim().slice(0, 40);
  return {i, visible, inert, name, box};
})
"""
_OBSERVE_JS: Final = """
() => { window.__mut = 0;
  document.addEventListener('change', () => { window.__mut += 1; }, true);  // checkbox, radio
  new MutationObserver(m => { window.__mut += m.length; })
  .observe(document.documentElement,
    {subtree: true, childList: true, attributes: true, characterData: true}); }
"""


def _page_url(root: Path, page: str, theme: str) -> str:
    return (root / page).resolve().as_uri() + f"?theme={theme}"


def render_checks(pkg: Package, manifest: Manifest, refs: Path | None) -> list[Finding]:
    allowed = [pkg.root.resolve().as_uri()] + (
        [pkg.base_root.resolve().as_uri()] if pkg.base_root else []
    )
    viewports: dict[str, set[int]] = {}
    for b in manifest.boards:
        viewports.setdefault(b.page, set()).add(b.viewport)
    load_problems: list[str] = []
    theme_problems: list[str] = []
    wiring_problems: list[str] = []
    parity_problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        def context(width: int, theme: str) -> Any:
            return browser.new_context(
                viewport={"width": width, "height": VIEWPORT_HEIGHT},
                color_scheme=cast("Literal['light', 'dark']", theme),
                reduced_motion="reduce",
                device_scale_factor=1,
            )

        for page in pkg.html():
            shots: dict[str, bytes] = {}
            for theme in THEMES:
                for width in sorted(viewports.get(page, {1440})):
                    ctx = context(width, theme)
                    pg = ctx.new_page()
                    errors: list[str] = []
                    pg.on(
                        "console",
                        lambda m, e=errors: e.append(m.text) if m.type == "error" else None,
                    )
                    pg.on("pageerror", lambda exc, e=errors: e.append(str(exc)))
                    pg.on("requestfailed", lambda r, e=errors: e.append(f"failed {r.url}"))
                    pg.on(
                        "request",
                        lambda r, e=errors: (
                            None
                            if r.url.startswith(("data:", "blob:"))
                            or any(r.url.startswith(a) for a in allowed)
                            else e.append(f"outside {r.url}")
                        ),
                    )
                    pg.goto(_page_url(pkg.root, page, theme), wait_until="load")
                    pg.evaluate("document.fonts.ready.then(() => undefined)")
                    if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                        errors.append("horizontal scroll")
                    load_problems.extend(f"{page} {width} {theme}: {e}" for e in errors)
                    if width == max(viewports.get(page, {1440})):
                        shots[theme] = pg.screenshot(
                            full_page=True, animations="disabled", caret="hide"
                        )
                    ctx.close()
            if shots.get("light") == shots.get("dark"):
                theme_problems.append(f"{page}: dark renders the same as light")
            wiring_problems.extend(_wiring(context, pkg.root, page))
        if refs is not None:
            parity_problems = _parity(context, pkg.root, manifest, refs)
        browser.close()
    findings = [
        _verdict(
            "render",
            load_problems,
            "no console error, failed or outside request, or horizontal scroll",
        ),
        _verdict("themes", theme_problems, "dark differs from light on every page"),
        _verdict("wiring", wiring_problems, "every visible control is wired"),
    ]
    if refs is not None:
        findings.append(
            _verdict("parity", parity_problems, f"{len(manifest.boards)} boards within tolerance")
        )
    return findings


def _wiring(context: Callable[[int, str], Any], root: Path, page: str) -> list[str]:
    problems: list[str] = []
    ctx = context(1440, "light")
    pg = ctx.new_page()
    url = _page_url(root, page, "light")
    pg.goto(url, wait_until="load")
    controls = [
        c for c in pg.evaluate(_CONTROLS_JS, _WIRED_SELECTOR) if c["visible"] and not c["inert"]
    ]
    for control in controls:
        pg.goto(url, wait_until="load")
        pg.evaluate(_OBSERVE_JS)
        before = pg.url
        try:
            target = pg.locator(_WIRED_SELECTOR).nth(control["i"])
            if control["box"]:  # custom boxes are visually hidden under their label
                target.evaluate("el => el.click()")
            else:
                target.click(timeout=2000)
            pg.wait_for_timeout(150)
            moved = pg.url != before
            changed = moved or pg.evaluate("window.__mut || 0") > 0
        except PlaywrightError as exc:
            problems.append(
                f"{page}: '{control['name']}' could not be clicked ({type(exc).__name__})"
            )
            continue
        if not changed:
            problems.append(
                f"{page}: '{control['name']}' does nothing (wire it or mark data-handoff-inert)"
            )
    ctx.close()
    return problems


def _diff_ratio() -> Callable[[Path, Path], float]:
    spec = importlib.util.spec_from_file_location(
        "visual_handoff", ROOT / "tests" / "visual" / "handoff.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("tests/visual/handoff.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn: Callable[[Path, Path], float] = module.diff_ratio
    return fn


def _parity(
    context: Callable[[int, str], Any], root: Path, manifest: Manifest, refs: Path
) -> list[str]:
    diff = _diff_ratio()
    problems: list[str] = []
    out = refs / "_actual"
    out.mkdir(parents=True, exist_ok=True)
    for b in manifest.boards:
        ref = refs / (b.artboard.removesuffix(".dc.html") + ".png")
        if not ref.is_file():
            problems.append(f"{b.artboard}: no reference {ref.name}")
            continue
        ctx = context(b.viewport, b.theme)
        pg = ctx.new_page()
        pg.goto(_page_url(root, b.page, b.theme), wait_until="load")
        pg.evaluate("document.fonts.ready.then(() => undefined)")
        actual = out / ref.name
        pg.screenshot(path=str(actual), full_page=True, animations="disabled", caret="hide")
        ctx.close()
        ratio = diff(ref, actual)
        limit = manifest.ratios.get(b.page, PARITY_RATIO)
        if ratio > limit:
            problems.append(f"{b.artboard} vs {b.page}: {ratio:.4%} differs (limit {limit:.2%})")
    return problems


# --- main ------------------------------------------------------------------------


def run(root: Path, *, render: bool, refs: Path | None, write_manifest: bool) -> list[Finding]:
    toml_path = root / "handoff.toml"
    if not toml_path.is_file():
        return [Finding("FAIL", "manifest", f"no handoff.toml in {root}")]
    manifest, problems = parse_manifest(tomllib.loads(toml_path.read_text()))
    if manifest is None:
        return [_verdict("manifest", problems, "")]
    pkg = load(root, manifest.base)
    sums = root.parent / f"{root.name}.sha256"
    recorded = sums.read_text() if sums.is_file() else None
    findings = [
        Finding("PASS", "manifest", f"{manifest.kind} {manifest.name}"),
        *static_checks(pkg, manifest, recorded),
    ]
    if render or refs is not None:
        findings += render_checks(pkg, manifest, refs)
    others_pass = all(f.level != "FAIL" for f in findings if f.check != "checksums")
    if write_manifest and others_pass:
        sums.write_text(manifest_lines(pkg.files))
        findings = [f for f in findings if f.check != "checksums"]
        findings.append(Finding("PASS", "checksums", f"wrote {sums.name}"))
    return findings


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", type=Path)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--parity", type=Path, default=None, metavar="REFS")
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    findings = run(
        args.package.resolve(),
        render=args.render,
        refs=args.parity,
        write_manifest=args.write_manifest,
    )
    for f in findings:
        print(f.line())
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
