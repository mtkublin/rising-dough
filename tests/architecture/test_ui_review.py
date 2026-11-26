# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G33: a UI-facing change passes the mechanical UI checks and carries a UI review verdict (ADR-0152 §3, T-DW11).

The branch diff against its base (``origin/main``, else ``main``) is checked by ``scripts/ci/check_ui.py``
(colours, lengths and tokens on the added lines of templates and static CSS/JS/SVG). When the diff touches a
UI file, the frontend audit record it adds (G31, ``docs/audits/<date>-<slug>.md``) must also carry the
``ui-reviewer`` agent's ``## UI review`` section with ``VERDICT: PASS``.

Skips cleanly outside a git checkout, when no base ref exists, or when HEAD is the base (CI on main).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.architecture._ratchet import REPO_ROOT

RECORD = re.compile(r"^docs/audits/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
REVIEW = re.compile(r"^## UI review\b(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
VERDICT = re.compile(r"^VERDICT:\s*(PASS|RETURN|ESCALATE)\b", re.MULTILINE)
TEACH = (
    "G33 UI review (ADR-0152): a UI-facing change passes `just check-ui` (tokens only: no colour literal, no "
    "literal spacing/radius/type length, every var() defined, no new design-system token outside "
    "docs/design/system/) and its docs/audits/<date>-<slug>.md record carries the `ui-reviewer` agent's "
    "'## UI review' section with 'VERDICT: PASS' (run /ui-review). RETURN means fix; ESCALATE means ask the operator."
)


def _check_ui() -> Any:
    spec = importlib.util.spec_from_file_location(
        "check_ui_guard", Path(REPO_ROOT) / "scripts/ci/check_ui.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def review_problems(ui_changed: list[str], records: dict[str, str]) -> list[str]:
    """Problems for a diff: UI files changed without a passing UI review in an audit record."""
    if not ui_changed:
        return []
    verdicts = []
    for name, text in sorted(records.items()):
        if not RECORD.match(name):
            continue
        section = REVIEW.search(text)
        found = VERDICT.search(section.group(1)) if section else None
        verdicts.append((name, found.group(1) if found else None))
    if any(v == "PASS" for _, v in verdicts):
        return []
    if not verdicts:
        return [
            f"{len(ui_changed)} UI file(s) changed (e.g. {ui_changed[0]}) but no docs/audits/<date>-<slug>.md"
        ]
    return [
        f"{name}: "
        + (f"UI review verdict is {v}" if v else "no '## UI review' section with a VERDICT line")
        for name, v in verdicts
    ]


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - git from PATH
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def test_ui_changes_pass_the_checks_and_carry_a_ui_review() -> None:
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        pytest.skip("not a git checkout")
    check_ui = _check_ui()
    base = next((b for ref in check_ui.BASES if (b := _git("merge-base", ref, "HEAD"))), None)
    if base is None or base == _git("rev-parse", "HEAD"):
        pytest.skip("no base ref to diff against, or HEAD is the base")
    names = _git("diff", "--name-only", f"{base}...HEAD")
    if names is None:
        pytest.skip("git diff unavailable")
    changed = [n for n in names.splitlines() if n]
    ui_changed = [n for n in changed if check_ui.is_ui_path(n)]
    if not ui_changed:
        return
    failed = [f.line() for f in check_ui.run(base) if f.level == "FAIL"]
    records = {
        n: (Path(REPO_ROOT) / n).read_text(encoding="utf-8")
        for n in changed
        if RECORD.match(n) and (Path(REPO_ROOT) / n).is_file()
    }
    problems = failed + review_problems(ui_changed, records)
    assert not problems, "\n" + TEACH + "\n" + "\n".join(f"  - {p}" for p in problems)


def test_review_check_needs_a_passing_verdict_in_a_record() -> None:
    template = "src/budget_planner/web/templates/today.html"
    record = "docs/audits/2026-11-26-today.md"
    assert review_problems([], {}) == []
    assert review_problems([template], {}) == [
        f"1 UI file(s) changed (e.g. {template}) but no docs/audits/<date>-<slug>.md"
    ]
    assert review_problems([template], {record: "## Routes\n1440\n"}) == [
        f"{record}: no '## UI review' section with a VERDICT line"
    ]
    escalated = "## UI review\n\nVERDICT: ESCALATE\n"
    assert review_problems([template], {record: escalated}) == [
        f"{record}: UI review verdict is ESCALATE"
    ]
    passed = "## Routes\n\n## UI review\n\nLAYERS ...\nVERDICT: PASS\n\n## Next\n"
    assert review_problems([template], {record: passed}) == []
    elsewhere = "## Routes\nVERDICT: PASS\n\n## UI review\n\nVERDICT: RETURN\n"
    assert review_problems([template], {record: elsewhere}) == [
        f"{record}: UI review verdict is RETURN"
    ]
