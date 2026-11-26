"""Mechanical half of the UI review (ADR-0152 §3, T-DW11).

Checks the lines a branch adds under ``src/budget_planner/web/templates/`` and
``src/budget_planner/web/static/`` against its merge base, and reports which design
reference layers apply (ADR-0152 §1).

FAIL ``colours``: a colour literal outside a ``tokens.css``.
FAIL ``lengths``: a literal length in a spacing, radius or type property.
FAIL ``tokens``: a ``var(--x)`` nothing defines, or a design-system token family
(``--color-`` ...) defined outside the system.
HINT: new template files, new ``.rd-<block>`` selectors that neither the system nor
the rest of the app defines, new component-scoped custom properties.
LAYERS: design system (always), base UI (on once ``static/rd/css/main.css`` is on the
base), handoff (``Design-Ref:`` commit trailers and ``docs/design/`` paths in the diff).

Output: ``PASS|FAIL <check>: <detail>``, ``HINT <kind>: <detail>`` and ``LAYERS ...``
lines. Exit 1 on any FAIL.

Usage: check_ui.py [--base REF]   (default: merge base with origin/main, else main)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess  # nosec B404
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
WEB: Final = "src/budget_planner/web/"
TEMPLATES: Final = WEB + "templates/"
STATIC: Final = WEB + "static/"
BASE_UI_MARKER: Final = STATIC + "rd/css/main.css"
SYSTEM: Final = ROOT / "docs/design/system/project"
BASES: Final = ("origin/main", "main")
UI_SUFFIXES: Final = (".html", ".css", ".js", ".svg")
# Bundles and vendored files are generated from sources the diff already shows.
GENERATED: Final = re.compile(r"(\.bundle\.css|/tailwind\.css|/vendor/.*|/fonts/.*)$")
SYSTEM_FAMILIES: Final = ("--color-", "--space-", "--radius-", "--font-", "--shadow-", "--size-")
LENGTH_PROPS: Final = re.compile(
    r"(?<![a-z-])(padding|margin|gap|row-gap|column-gap|inset|border-radius|font-size|"
    r"line-height|letter-spacing)(?:-[a-z-]+)?\s*:\s*([^;{}\"']+)",
    re.IGNORECASE,
)
_LENGTH: Final = re.compile(r"(?<![\w-])\d*\.?\d+(?:px|rem|em)\b")
_VAR_USE: Final = re.compile(r"var\(\s*(--[a-z0-9-]+)", re.IGNORECASE)
_PROP_DEF: Final = re.compile(r"(?<![\w-])(--[a-z0-9-]+)\s*:", re.IGNORECASE)
_RD_SELECTOR: Final = re.compile(r"\.(rd-[a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])")
_HUNK: Final = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
_DESIGN_REF: Final = re.compile(r"^Design-Ref:\s*(\S+)", re.MULTILINE)
MAX_SHOWN: Final = 20
# Data palettes carry literal colours by design (the base package's category presets, ADR-0107 §5).
PALETTES: Final = frozenset({"category-colors.css"})
# Images (the favicon, illustrations) are drawn in brand colours; icons use currentColor.
IMAGES: Final = re.compile(r"/img/|/favicon\.svg$")
MIN_REF_PARTS: Final = 4  # docs/design/<package or specs>/<file>
NOT_PACKAGES: Final = frozenset({"system", "specs", "requests"})


@dataclass(frozen=True)
class Finding:
    level: str  # PASS, FAIL or HINT
    check: str
    detail: str = ""

    def line(self) -> str:
        return f"{self.level} {self.check}" + (f": {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Change:
    """One UI file the branch adds or modifies: its text now and its added line numbers."""

    path: str
    text: str
    added: frozenset[int]
    new_file: bool


def _colour_literals() -> Callable[[str, str], list[str]]:
    spec = importlib.util.spec_from_file_location(
        "check_handoff_ui", ROOT / "scripts/ci/check_handoff.py"
    )
    if spec is None or spec.loader is None:
        msg = "scripts/ci/check_handoff.py not loadable"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    fn: Callable[[str, str], list[str]] = module.colour_literals
    return fn


def is_ui_path(path: str) -> bool:
    ui = path.startswith(TEMPLATES) or (path.startswith(STATIC) and path.endswith(UI_SUFFIXES))
    return ui and not GENERATED.search(path)


def added_lines(diff: str) -> dict[str, frozenset[int]]:
    """Added line numbers per file from a ``git diff -U0`` text."""
    found: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            if current is not None:
                found.setdefault(current, set())
            continue
        m = _HUNK.match(line)
        if m and current is not None:
            start, count = int(m.group(1)), int(m.group(2) or "1")
            found[current].update(range(start, start + count))
    return {path: frozenset(lines) for path, lines in found.items()}


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _comment_free(text: str) -> str:
    """CSS and HTML comments blanked to same-length spaces, so line numbers stay put."""
    return re.sub(
        r"/\*.*?\*/|<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.DOTALL
    )


def check_colours(changes: Iterable[Change], literals: Callable[[str, str], list[str]]) -> Finding:
    hits = [
        hit
        for c in changes
        if c.path.rsplit("/", 1)[-1] not in PALETTES and not IMAGES.search(c.path)
        for hit in literals(c.path, c.text)
        if int(hit.split(":")[1].split()[0]) in c.added
    ]
    return _verdict("colours", hits, "colours from tokens only")


def length_literals(change: Change) -> list[str]:
    """Literal lengths in spacing, radius and type properties on added lines."""
    if change.path.endswith("tokens.css") or not change.path.endswith((".css", ".html")):
        return []
    text = _comment_free(change.text)
    hits: list[str] = []
    for m in LENGTH_PROPS.finditer(text):
        line = _line_of(text, m.start())
        if line not in change.added:
            continue
        value = re.sub(r"var\([^)]*\)", "", m.group(2))
        hits.extend(
            f"{change.path}:{line} {m.group(1)}: {n.group()}"
            for n in _LENGTH.finditer(value)
            if float(re.sub(r"[a-z]+$", "", n.group())) != 0
        )
    return hits


def check_lengths(changes: Iterable[Change]) -> Finding:
    hits = [hit for c in changes for hit in length_literals(c)]
    return _verdict("lengths", hits, "spacing, radius and type from tokens only")


def defined_properties(texts: Iterable[str]) -> set[str]:
    return {name for text in texts for name in _PROP_DEF.findall(_comment_free(text))}


def check_tokens(changes: Iterable[Change], defined: set[str], system: set[str]) -> Finding:
    problems: list[str] = []
    for c in changes:
        text = _comment_free(c.text)
        for m in _VAR_USE.finditer(text):
            line = _line_of(text, m.start())
            if line in c.added and m.group(1) not in defined:
                problems.append(f"{c.path}:{line} {m.group(1)} is not defined")
        for m in _PROP_DEF.finditer(text):
            line = _line_of(text, m.start())
            name = m.group(1)
            if line in c.added and name.startswith(SYSTEM_FAMILIES) and name not in system:
                problems.append(
                    f"{c.path}:{line} {name} is a design-system token the system lacks "
                    "(new tokens go through /designer)"
                )
    return _verdict("tokens", problems, "every token defined; no system token outside the system")


def without_added(change: Change) -> str:
    """The file's text with its added lines blanked: what it looked like before (near enough)."""
    return "\n".join(
        "" if n in change.added else line for n, line in enumerate(change.text.split("\n"), 1)
    )


def existing_blocks(app_css: Mapping[str, str], changes: Iterable[Change]) -> set[str]:
    """``rd-*`` blocks the app defines outside the lines this change adds."""
    changed = {c.path: without_added(c) for c in changes}
    return {b for path, css in app_css.items() for b in blocks(changed.get(path, css))}


def hints(changes: Iterable[Change], system: set[str], known_blocks: set[str]) -> list[Finding]:
    found: list[Finding] = []
    for c in changes:
        text = _comment_free(c.text)
        if c.new_file and c.path.startswith(TEMPLATES):
            found.append(Finding("HINT", "new-template", c.path))
        if not c.path.endswith(".css"):
            continue
        for m in _RD_SELECTOR.finditer(text):
            line = _line_of(text, m.start())
            block = m.group(1).split("__")[0]
            if line in c.added and block not in known_blocks:
                found.append(Finding("HINT", "new-component", f"{c.path}:{line} .{block}"))
        for m in _PROP_DEF.finditer(text):
            line = _line_of(text, m.start())
            name = m.group(1)
            if line in c.added and name not in system and not name.startswith(SYSTEM_FAMILIES):
                found.append(Finding("HINT", "new-property", f"{c.path}:{line} {name}"))
    # One hint per block or property: the first line that introduces it.
    first: dict[tuple[str, str], Finding] = {}
    for f in found:
        first.setdefault(
            (f.check, f.detail.split(" ")[-1] if f.check != "new-template" else f.detail), f
        )
    return sorted(first.values(), key=lambda f: (f.check, f.detail))


def blocks(css: str) -> set[str]:
    """``rd-*`` block names a stylesheet defines."""
    return {m.group(1).split("__")[0] for m in _RD_SELECTOR.finditer(_comment_free(css))}


def handoff_refs(changed: Iterable[str]) -> set[str]:
    """Specs and handoff packages a diff touches (not the system or the folder docs)."""
    refs: set[str] = set()
    for path in changed:
        parts = path.split("/")
        if len(parts) < MIN_REF_PARTS or parts[:2] != ["docs", "design"]:
            continue
        if parts[2] == "specs" and parts[3] != "README.md":
            refs.add(path)
        elif parts[2] not in NOT_PACKAGES:
            refs.add("/".join(parts[:3]))
    return refs


def layers(base_ui: bool, commit_messages: str, changed: Iterable[str]) -> Finding:
    refs = sorted(set(_DESIGN_REF.findall(commit_messages)) | handoff_refs(changed))
    return Finding(
        "LAYERS",
        "design-system=on",
        f"base-ui={'on' if base_ui else 'off'} handoff={','.join(refs) or 'none'}",
    )


def _verdict(check: str, problems: Sequence[str], ok: str) -> Finding:
    if not problems:
        return Finding("PASS", check, ok)
    shown = list(problems[:MAX_SHOWN])
    more = f" (+{len(problems) - MAX_SHOWN} more)" if len(problems) > MAX_SHOWN else ""
    return Finding("FAIL", check, "; ".join(shown) + more)


def system_tokens(system: Path) -> set[str]:
    tokens = json.loads((system / "tokens.json").read_text(encoding="utf-8"))
    names = {
        f"--{t['name']}"
        for family in tokens.values()
        if isinstance(family, Mapping)
        for t in family.get("tokens", [])
    }
    families = tokens.get("type", {}).get("families", {})
    names |= {f"--font-{key}" for key in families}
    return names | defined_properties(
        [(system / "components/bundle.css").read_text(encoding="utf-8")]
    )


def review(
    changes: Sequence[Change],
    *,
    app_css: Mapping[str, str],
    templates: Iterable[str],
    system: Path,
    base_ui: bool,
    commit_messages: str,
    changed: Iterable[str],
) -> list[Finding]:
    bundle = (system / "components/bundle.css").read_text(encoding="utf-8")
    known = system_tokens(system)
    defined = known | defined_properties([*app_css.values(), *templates])
    known_blocks = blocks(bundle) | existing_blocks(app_css, changes)
    return [
        layers(base_ui, commit_messages, changed),
        check_colours(changes, _colour_literals()),
        check_lengths(changes),
        check_tokens(changes, defined, known),
        *hints(changes, known, known_blocks),
    ]


def _git(*args: str) -> str:
    done = subprocess.run(  # noqa: S603  # nosec B603 B607 (fixed git argv, no shell)
        ["git", *args],  # noqa: S607 - git from PATH, as check_item.py
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout


def merge_base(ref: str | None) -> str:
    for candidate in (ref,) if ref else BASES:
        try:
            return _git("merge-base", candidate, "HEAD").strip()
        except subprocess.CalledProcessError:
            continue
    msg = f"no merge base with {ref or ' or '.join(BASES)}"
    raise RuntimeError(msg)


def branch_changes(base: str) -> tuple[list[Change], list[str]]:
    """UI changes between ``base`` and the working tree, and every changed path."""
    status = [line.split("\t") for line in _git("diff", "--name-status", base).splitlines() if line]
    changed = [parts[-1] for parts in status]
    new = {parts[-1] for parts in status if parts[0].startswith("A")}
    ui = [p for p in changed if is_ui_path(p) and (ROOT / p).is_file()]
    added = added_lines(_git("diff", "-U0", base, "--", *ui)) if ui else {}
    changes = [
        Change(p, (ROOT / p).read_text(encoding="utf-8"), added.get(p, frozenset()), p in new)
        for p in ui
    ]
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", WEB).splitlines()
    for p in untracked:
        if is_ui_path(p):
            text = (ROOT / p).read_text(encoding="utf-8")
            changes.append(Change(p, text, frozenset(range(1, text.count("\n") + 2)), True))
            changed.append(p)
    return changes, changed


def run(ref: str | None) -> list[Finding]:
    base = merge_base(ref)
    changes, changed = branch_changes(base)
    static = ROOT / STATIC
    app_css = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(static.rglob("*.css"))
        if not GENERATED.search(p.as_posix())
    }
    templates = [p.read_text(encoding="utf-8") for p in sorted((ROOT / TEMPLATES).rglob("*.html"))]
    try:
        _git("cat-file", "-e", f"{base}:{BASE_UI_MARKER}")
        base_ui = True
    except subprocess.CalledProcessError:
        base_ui = False
    return review(
        changes,
        app_css=app_css,
        templates=templates,
        system=SYSTEM,
        base_ui=base_ui,
        commit_messages=_git("log", "--format=%B", f"{base}..HEAD"),
        changed=changed,
    )


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=None, help="ref to diff against (merge base is used)")
    args = parser.parse_args(argv)
    findings = run(args.base)
    for f in findings:
        print(f.line())
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
