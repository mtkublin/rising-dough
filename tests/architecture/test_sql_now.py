# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G32: no SQLite clock in runtime SQL (ADR-0140 amendment 2026-11-23, T-Q311).

``date('now')``, ``datetime('now')``, ``strftime(..., 'now')``, ``CURRENT_TIMESTAMP``, ``CURRENT_DATE`` and
``CURRENT_TIME`` read the host clock behind ``budget_planner.clock`` and so ignore ``clock.frozen``: a test that
pins time still gets the wall date in the stored row. Pass ``clock.utc_now_iso()`` (or a date from the caller) as a
bound parameter instead.

Scope: every string literal under ``src/``. ``migrations/`` is excluded: migrations run once, in order, as immutable
history (ADR-0007), so a ``DEFAULT (strftime(..., 'now'))`` column fallback or a one-off backfill (0015) is not a
runtime query. Zero violations, no allowlist.
"""

from __future__ import annotations

import ast
import re

from tests.architecture._ratchet import REPO_ROOT, SRC_ROOT, parse_file

TEACH = (
    "G32 no SQL clock: bind clock.utc_now_iso() / a date argument as a parameter instead of SQLite's own "
    "'now' / CURRENT_* (ADR-0140 amendment 2026-11-23, T-Q311)."
)
_NOW = re.compile(r"'now'|\bCURRENT_(?:TIMESTAMP|DATE|TIME)\b", re.IGNORECASE)


def scan_source(source: str, shown: str) -> list[str]:
    """Violations in the string literals of one Python module (docstrings skipped)."""
    return scan_tree(ast.parse(source), shown)


def scan_tree(tree: ast.Module, shown: str) -> list[str]:
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        f"{shown}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and _NOW.search(node.value)
    ]


def collect() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        shown = path.relative_to(REPO_ROOT).as_posix()
        if shown.endswith("src/budget_planner/clock.py"):
            continue
        found.extend(scan_tree(parse_file(path), shown))
    return found


def test_no_sqlite_clock_in_runtime_sql() -> None:
    assert collect() == [], TEACH


def test_detects_now_in_a_python_string() -> None:
    src = "def f(c):\n    c.execute(\"UPDATE t SET at = datetime('now')\")\n"
    assert scan_source(src, "x.py") == ["x.py:2"]


def test_detects_current_timestamp_and_skips_docstrings() -> None:
    src = '"""mentions \'now\' here"""\nQ = "SELECT CURRENT_TIMESTAMP"\n'
    assert scan_source(src, "x.py") == ["x.py:2"]
