# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G31: a change that touches templates or CSS carries a frontend-visual-audit record (T-Q16 dry run V1/V2b).

Agents skipped the mandatory ``frontend-visual-audit`` skill twice (ad-hoc Playwright; no audit at all), so the
rule became a guard: when the branch diff against its base touches ``src/budget_planner/web/templates/**`` or
``src/budget_planner/web/static/**/*.css``, it must add or update ``docs/audits/<date>-<slug>.md`` with the routes,
the 1440/1024/375 viewports, the five diagnostics and screenshot paths (format: the skill, Step 6).

Base = merge-base with ``audit/quality``, else ``origin/main``, else ``main``. Skips cleanly outside a git
checkout, when no base ref exists, or when HEAD is the base (CI on main).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.architecture._ratchet import REPO_ROOT

BASES = ("audit/quality", "origin/main", "main")
FRONTEND = re.compile(r"^src/budget_planner/web/(templates/.+|static/.+\.css)$")
RECORD = re.compile(r"^docs/audits/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
VIEWPORTS = ("1440", "1024", "375")
DIAGNOSTICS = (
    "horizontalScroll",
    "overflowingElements",
    "duplicateIds",
    "consoleErrors",
    "requestFailures",
)
TEACH = (
    "G31 frontend audit: this change touches templates/CSS, so run the `frontend-visual-audit` skill and commit "
    "its record as docs/audits/<YYYY-MM-DD>-<slug>.md (routes, viewports 1440/1024/375, the five diagnostics "
    "horizontalScroll, overflowingElements, duplicateIds, consoleErrors, requestFailures, and screenshot paths; "
    "format: skill Step 6). Ad-hoc Playwright does not count."
)


def audit_problems(changed: list[str], records: dict[str, str]) -> list[str]:
    """Problems for a diff: frontend files changed without a complete audit record."""
    touched = [f for f in changed if FRONTEND.match(f)]
    if not touched:
        return []
    found = {name: text for name, text in records.items() if RECORD.match(name)}
    if not found:
        return [
            f"{len(touched)} frontend file(s) changed (e.g. {touched[0]}) but no docs/audits/<date>-<slug>.md"
        ]
    problems: list[str] = []
    for name, text in found.items():
        missing = [
            t for t in (*VIEWPORTS, *DIAGNOSTICS, "screenshot") if t.lower() not in text.lower()
        ]
        if not missing:
            return []
        problems.append(f"{name} lacks: {', '.join(missing)}")
    return problems


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


def _merge_base() -> str | None:
    for ref in BASES:
        base = _git("merge-base", ref, "HEAD")
        if base:
            return base
    return None


def test_frontend_changes_carry_an_audit_record() -> None:
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        pytest.skip("not a git checkout")
    base = _merge_base()
    if base is None or base == _git("rev-parse", "HEAD"):
        pytest.skip("no base ref to diff against, or HEAD is the base")
    names = _git("diff", "--name-only", f"{base}...HEAD")
    if names is None:
        pytest.skip("git diff unavailable")
    changed = [n for n in names.splitlines() if n]
    records = {
        n: (Path(REPO_ROOT) / n).read_text(encoding="utf-8")
        for n in changed
        if RECORD.match(n) and (Path(REPO_ROOT) / n).is_file()
    }
    problems = audit_problems(changed, records)
    assert not problems, "\n" + TEACH + "\n" + "\n".join(f"  - {p}" for p in problems)


def test_audit_record_check_detects_missing_and_incomplete_records() -> None:
    template = "src/budget_planner/web/templates/today.html"
    assert audit_problems(["src/budget_planner/services/x.py"], {}) == []
    assert audit_problems([template], {})
    good = "routes 1440 1024 375 " + " ".join(DIAGNOSTICS) + " screenshot: shots/a.png"
    assert (
        audit_problems(
            [template, "docs/audits/2026-11-20-today.md"], {"docs/audits/2026-11-20-today.md": good}
        )
        == []
    )
    assert audit_problems([template], {"docs/audits/2026-11-20-today.md": "routes only"})
    css = "src/budget_planner/web/static/rd/css/app.bundle.css"
    assert audit_problems([css], {})
