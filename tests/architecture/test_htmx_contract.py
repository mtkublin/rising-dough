# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G12: HTMX emitter/listener contract (Q-038, Q-037; ADR-0130).

Builds the matrix of server-emitted custom events (``trigger(...)`` arguments, ``*-stale`` literals and ``toast``
payloads in ``web/**/*.py``) against client listeners (``hx-trigger="<event> from:body"`` in templates and
``addEventListener("<event>")`` in ``static/js``), and checks static ``hx-target`` ids. Rules:

* ``orphan-emitter``: an event is emitted but nothing listens (count = emit sites);
* ``orphan-listener``: something listens for an event nothing emits;
* ``target-missing``: a static ``hx-target="#id"`` that no template defines;
* ``toast-kind``: a toast payload uses ``kind`` while the listener (``app-init.js``) reads ``variant``.

Not detected (inventory section 17): OOB ids resolved only at runtime, and ids created by JavaScript.
Allowlist: ``allowlists/htmx_events.toml``. A new template starts with no allowance.
"""

from __future__ import annotations

import ast
import re
from collections import Counter

from tests.architecture._ratchet import REPO_ROOT, SRC_ROOT, Violation, assert_ratchet, parse_file

GUARD = "htmx_events"
HEADER = "G12 htmx_events: HTMX events emitted without listeners (and vice versa), missing hx-target ids, toast shape (Q-038)."
WEB = SRC_ROOT / "web"
STALE = re.compile(r"^[a-z]+(?:-[a-z]+)*-stale$")
HX_TRIGGER = re.compile(r'hx-trigger="([^"]*)"')
HX_TARGET = re.compile(r'hx-target="(#[A-Za-z][\w-]*)"')
ID_ATTR = re.compile(r'\bid="([^"]+)"')
LISTENER = re.compile(r"""addEventListener\(\s*["']([a-z]+(?:-[a-z]+)*)["']""")
DOM_EVENTS = frozenset(
    {
        "click",
        "change",
        "input",
        "submit",
        "keydown",
        "keyup",
        "focus",
        "blur",
        "scroll",
        "resize",
        "beforeinput",
        "load",
    }
)
TEACH = (
    'G12 HTMX contract: every emitted event needs a listener (`hx-trigger="<event> from:body"` or JS) and vice versa; '
    "every static hx-target needs an element with that id; toast payloads use `variant`. Use web/htmx.py names, do not "
    "hand-build HX-Trigger JSON (Q-038, ADR-0130)."
)


def emitted_events(tree: ast.Module) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and STALE.match(node.value)
        ):
            counts[node.value] += 1
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == "toast":
                    counts["toast"] += 1
    return counts


def toast_kind_sites(tree: ast.Module) -> int:
    sites = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            is_toast = isinstance(key, ast.Constant) and key.value == "toast"
            if (
                is_toast
                and isinstance(value, ast.Dict)
                and any(isinstance(k, ast.Constant) and k.value == "kind" for k in value.keys)
            ):
                sites += 1
    return sites


def listened_events(templates: dict[str, str], scripts: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in templates.values():
        for attr in HX_TRIGGER.findall(text):
            for part in attr.split(","):
                if "from:body" in part and part.split():
                    counts[part.split()[0]] += 1
    for text in scripts.values():
        for name in LISTENER.findall(text):
            if name not in DOM_EVENTS:
                counts[name] += 1
    return counts


def scan(
    py_trees: dict[str, ast.Module], templates: dict[str, str], scripts: dict[str, str]
) -> list[Violation]:
    emitted: Counter[str] = Counter()
    toast_kind: Counter[str] = Counter()
    for rel, tree in py_trees.items():
        emitted.update(emitted_events(tree))
        if sites := toast_kind_sites(tree):
            toast_kind[rel] = sites
    listened = listened_events(templates, scripts)
    found = [
        Violation(f"event:{name}", 0, "orphan-emitter", "")
        for name, n in emitted.items()
        for _ in range(n)
        if name not in listened
    ]
    found += [
        Violation(f"event:{name}", 0, "orphan-listener", "")
        for name, n in listened.items()
        for _ in range(n)
        if name not in emitted
    ]
    found += [
        Violation(rel, 0, "toast-kind", "") for rel, n in toast_kind.items() for _ in range(n)
    ]
    ids = {i for text in templates.values() for i in ID_ATTR.findall(text)}
    for rel, text in templates.items():
        for target in HX_TARGET.findall(text):
            if target[1:] not in ids:
                found.append(Violation(rel, 0, "target-missing", target))
    return found


def collect() -> list[Violation]:
    py_trees = {
        p.relative_to(REPO_ROOT).as_posix(): parse_file(p)
        for p in sorted(WEB.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    templates = {
        p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted((WEB / "templates").rglob("*.html"))
    }
    scripts: dict[str, str] = {
        p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in [*sorted((WEB / "static" / "js").glob("*.js")), WEB / "static" / "htmx-csrf.js"]
    }
    return scan(py_trees, templates, scripts)


def meta(v: Violation) -> tuple[str, str, str, str]:
    return "entry", "Q-038", "E03", ""


def test_htmx_contract_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_htmx_contract_detects_fixture_violations() -> None:
    tree = ast.parse(
        'def f(r):\n    trigger(r, "ghost-stale")\n    return {"toast": {"kind": "ok", "message": "m"}}\n'
    )
    templates = {
        "t.html": '<div hx-get="/x" hx-target="#nowhere" hx-trigger="never-stale from:body"></div>'
    }
    rules = Counter(v.rule for v in scan({"p.py": tree}, templates, {}))
    assert rules["orphan-emitter"] == 2  # ghost-stale and toast (no listener in this fixture)
    assert rules["orphan-listener"] == 1
    assert rules["target-missing"] == 1
    assert rules["toast-kind"] == 1
