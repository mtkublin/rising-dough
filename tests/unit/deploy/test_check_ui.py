"""scripts/ci/check_ui.py: the mechanical half of the UI review (ADR-0152 §3, T-DW11)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_ui", ROOT / "scripts/ci/check_ui.py")
assert _spec is not None and _spec.loader is not None
check_ui = importlib.util.module_from_spec(_spec)
sys.modules["check_ui"] = check_ui
_spec.loader.exec_module(check_ui)

CSS = "src/budget_planner/web/static/rd/css/components/goal.css"
TEMPLATE = "src/budget_planner/web/templates/goals/index.html"


def change(path: str, text: str, added: set[int] | None = None, *, new: bool = False) -> Any:
    """A ``check_ui.Change``; every line added unless ``added`` says which."""
    lines = set(range(1, text.count("\n") + 2)) if added is None else added
    return check_ui.Change(path, text, frozenset(lines), new)


def test_ui_paths_skip_generated_and_vendored_files() -> None:
    assert check_ui.is_ui_path(CSS)
    assert check_ui.is_ui_path(TEMPLATE)
    assert check_ui.is_ui_path("src/budget_planner/web/static/rd/js/dialog.js")
    assert not check_ui.is_ui_path("src/budget_planner/web/static/rd/css/app.bundle.css")
    assert not check_ui.is_ui_path("src/budget_planner/web/static/tailwind.css")
    assert not check_ui.is_ui_path("src/budget_planner/web/static/vendor/htmx.min.js")
    assert not check_ui.is_ui_path("src/budget_planner/web/routers/goals.py")


def test_added_lines_come_from_the_new_side_of_each_hunk() -> None:
    diff = (
        "diff --git a/x.css b/x.css\n--- a/x.css\n+++ b/x.css\n"
        "@@ -3,0 +4,2 @@\n+a\n+b\n@@ -9 +11 @@\n-c\n+d\n"
        "diff --git a/gone.css b/gone.css\n--- a/gone.css\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
    )
    assert check_ui.added_lines(diff) == {"x.css": frozenset({4, 5, 11})}


def test_colours_only_on_added_lines_and_never_in_palettes_or_images() -> None:
    css = ".rd-goal { color: #fff; }\n.rd-goal__bar { color: rgb(1 2 3); }\n"
    literals = check_ui._colour_literals()
    found = check_ui.check_colours([change(CSS, css, {2})], literals)
    assert found == check_ui.Finding("FAIL", "colours", f"{CSS}:2 rgb(")
    palette = "src/budget_planner/web/static/rd/css/components/category-colors.css"
    favicon = "src/budget_planner/web/static/rd/img/favicon.svg"
    svg = '<svg><path fill="#ff5a1f"/></svg>'
    assert check_ui.check_colours([change(palette, css), change(favicon, svg)], literals).level == (
        "PASS"
    )


def test_lengths_fail_on_literals_but_not_on_tokens_zero_or_old_lines() -> None:
    css = (
        ".a { padding: var(--space-2) 12px; }\n"
        ".b { margin: 0; gap: 0px; border-radius: var(--radius-sm, 4px); }\n"
        ".c { font-size: 0.875rem; }\n"
        "/* padding: 3px */\n"
        ".d { width: 40px; }\n"
    )
    assert check_ui.length_literals(change(CSS, css, {1, 2, 4, 5})) == [f"{CSS}:1 padding: 12px"]
    assert check_ui.length_literals(change(CSS, css, {3})) == [f"{CSS}:3 font-size: 0.875rem"]
    tokens = "src/budget_planner/web/static/rd/css/tokens.css"
    assert check_ui.length_literals(change(tokens, ":root { --space-2: 8px; }")) == []


def test_tokens_must_be_defined_and_system_families_stay_in_the_system() -> None:
    css = (
        ".a { color: var(--color-ink); }\n"
        ".b { color: var(--color-muted); }\n"
        ".c { --color-goal: var(--color-bake); --goal-fill: 40%; }\n"
    )
    found = check_ui.check_tokens(
        [change(CSS, css)], {"--color-ink", "--color-bake", "--goal-fill"}, {"--color-ink"}
    )
    assert found.level == "FAIL"
    assert found.detail == (
        f"{CSS}:2 --color-muted is not defined; "
        f"{CSS}:3 --color-goal is a design-system token the system lacks "
        "(new tokens go through /designer)"
    )


def test_hints_name_new_templates_components_and_properties_once() -> None:
    css = ".rd-btn { gap: var(--space-1); }\n.rd-goal { --goal-fill: 1; }\n.rd-goal__bar { }\n"
    found = check_ui.hints(
        [change(CSS, css), change(TEMPLATE, "<p></p>", new=True)],
        {"--space-1"},
        {"rd-btn"},
    )
    assert [f.line() for f in found] == [
        f"HINT new-component: {CSS}:2 .rd-goal",
        f"HINT new-property: {CSS}:2 --goal-fill",
        f"HINT new-template: {TEMPLATE}",
    ]


def test_existing_blocks_ignore_the_lines_a_change_adds() -> None:
    old = ".rd-goal { }\n"
    now = old + ".rd-new { }\n"
    app = {CSS: now, "other.css": ".rd-chip { }"}
    assert check_ui.existing_blocks(app, [change(CSS, now, {2})]) == {"rd-goal", "rd-chip"}


def test_layers_report_base_ui_and_handoff_references() -> None:
    changed = [
        "docs/design/goals/pages/goals/goals.html",
        "docs/design/specs/goals.md",
        "docs/design/specs/README.md",
        "docs/design/system/project/tokens.json",
        "docs/design/README.md",
    ]
    found = check_ui.layers(
        True, "feat: x\n\nDesign-Ref: docs/design/rising-dough-frontend\n", changed
    )
    assert found.line() == (
        "LAYERS design-system=on: base-ui=on handoff="
        "docs/design/goals,docs/design/rising-dough-frontend,docs/design/specs/goals.md"
    )
    assert check_ui.layers(False, "", []).line() == (
        "LAYERS design-system=on: base-ui=off handoff=none"
    )


def test_review_reads_the_system_tokens_and_bundle(tmp_path: Path) -> None:
    (tmp_path / "components").mkdir()
    tokens = {
        "color": {"tokens": [{"name": "color-ink", "value": {"light": "#000", "dark": "#fff"}}]},
        "spacing": {"tokens": [{"name": "space-1", "value": "4px"}]},
        "type": {"families": {"display": "Unbounded"}, "tokens": []},
    }
    (tmp_path / "tokens.json").write_text(json.dumps(tokens))
    (tmp_path / "components/bundle.css").write_text(".rd-btn { --btn-pad: 1px; }")
    css = ".rd-btn { color: var(--color-ink); padding: var(--btn-pad); font: var(--font-display); }"
    findings = check_ui.review(
        [change(CSS, css)],
        app_css={CSS: css},
        templates=[],
        system=tmp_path,
        base_ui=False,
        commit_messages="",
        changed=[CSS],
    )
    assert [f.line() for f in findings] == [
        "LAYERS design-system=on: base-ui=off handoff=none",
        "PASS colours: colours from tokens only",
        "PASS lengths: spacing, radius and type from tokens only",
        "PASS tokens: every token defined; no system token outside the system",
    ]
