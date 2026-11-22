# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G12: HTMX emitter/listener contract (Q-038, Q-037; ADR-0130, ADR-0142). Strict: zero allowlist entries.

``web/htmx.py`` defines ``Event`` (the wire names). Emitters are ``Event.<NAME>`` references and ``toast=`` keyword
arguments in ``web/**/*.py`` outside ``htmx.py``; listeners are ``hx-trigger="<event> from:body"`` in templates and
``addEventListener("<event>")`` in ``static/js``. Rules:

* ``orphan-emitter``: an event is emitted but nothing listens (count = emit sites);
* ``orphan-listener``: something listens for an application event nothing emits;
* ``unused-event``: an ``Event`` member no router emits;
* ``raw-trigger``: a ``HX-Trigger`` header write or a ``*-stale`` string literal outside ``web/htmx.py``;
* ``target-missing``: a static ``hx-target="#id"`` that no template defines.

Not detected (inventory section 17): OOB ids resolved only at runtime, and ids created by JavaScript.
"""

from __future__ import annotations

import ast
import re
from collections import Counter

from tests.architecture._ratchet import REPO_ROOT, SRC_ROOT, Violation, assert_ratchet, parse_file

GUARD = "htmx_events"
HEADER = "G12 htmx_events: strict, no entries (ADR-0142)."
WEB = SRC_ROOT / "web"
HTMX_MODULE = "src/budget_planner/web/htmx.py"
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
        "mousedown",
        "paste",
    }
)
TEACH = (
    'G12 HTMX contract: every emitted event needs a listener (`hx-trigger="<event> from:body"` or JS) and vice versa; '
    "every static hx-target needs an element with that id. Emit only through web/htmx.py (`trigger`, `Event`, "
    "`toast_payload`); never write the HX-Trigger header or a `*-stale` literal in a router (Q-038, ADR-0142)."
)


def event_members(tree: ast.Module) -> dict[str, str]:
    """``{MEMBER: wire-name}`` from the ``Event`` class in ``web/htmx.py``."""
    members: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Event":
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    members[stmt.targets[0].id] = stmt.value.value
    return members


def emitted_events(tree: ast.Module, members: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Event"
            and node.attr in members
        ):
            counts[members[node.attr]] += 1
        elif isinstance(node, ast.keyword) and node.arg == "toast":
            counts[members.get("TOAST", "toast")] += 1
    return counts


def raw_trigger_sites(tree: ast.Module) -> int:
    sites = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (node.value == "HX-Trigger" or STALE.match(node.value))
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
    members = event_members(py_trees[HTMX_MODULE]) if HTMX_MODULE in py_trees else {}
    emitted: Counter[str] = Counter()
    found: list[Violation] = []
    for rel, tree in py_trees.items():
        if rel == HTMX_MODULE:
            continue
        emitted.update(emitted_events(tree, members))
        found += [Violation(rel, 0, "raw-trigger", "") for _ in range(raw_trigger_sites(tree))]
    listened = listened_events(templates, scripts)
    found += [
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
        Violation(f"event:{value}", 0, "unused-event", "")
        for value in members.values()
        if value not in emitted
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


def test_htmx_contract_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_htmx_contract_detects_fixture_violations() -> None:
    htmx = ast.parse(
        'class Event(StrEnum):\n    GHOST_STALE = "ghost-stale"\n    SPARE_STALE = "spare-stale"\n'
        '    TOAST = "toast"\n'
    )
    router = ast.parse(
        "def f(r):\n    trigger(r, Event.GHOST_STALE)\n"
        '    r.headers["HX-Trigger"] = "{}"\n    return "never-stale"\n'
    )
    templates = {
        "t.html": '<div hx-get="/x" hx-target="#nowhere" hx-trigger="never-stale from:body"></div>'
    }
    trees = {HTMX_MODULE: htmx, "p.py": router}
    rules = Counter(v.rule for v in scan(trees, templates, {}))
    assert rules["orphan-emitter"] == 1  # ghost-stale has no listener
    assert rules["orphan-listener"] == 1  # never-stale has no emitter
    assert rules["unused-event"] == 2  # spare-stale and toast
    assert rules["raw-trigger"] == 2  # HX-Trigger header literal and a stale literal
    assert rules["target-missing"] == 1
