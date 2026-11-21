"""Audit-free repository helpers are importable only from ``services/recurring.py``.

ADR-0022 amendment 2026-11-21 (T-Q228, Q-049). ``repositories/_unaudited.py`` holds
UPDATEs that skip ``audit_log`` by design; the one service that orchestrates them
writes the paired audit row. Any other module in ``src/`` importing it would
silently bypass ADR-0019. Tests are out of scope (they seed state with the helpers).
"""

from __future__ import annotations

import ast

from tests.architecture._ratchet import parse_file, repo_rel, src_files

MODULE = "budget_planner.repositories._unaudited"
ALLOWED = "src/budget_planner/services/recurring.py"


def _imports_unaudited(tree: ast.Module) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == MODULE or (
                module == "budget_planner.repositories"
                and any(a.name == "_unaudited" for a in node.names)
            ):
                lines.append(node.lineno)
        elif isinstance(node, ast.Import):
            lines.extend(node.lineno for a in node.names if a.name == MODULE)
    return lines


def test_unaudited_helpers_are_imported_only_by_the_recurring_service() -> None:
    offenders = [
        f"{repo_rel(path)}:{line}"
        for path in src_files()
        if repo_rel(path) != ALLOWED
        for line in _imports_unaudited(parse_file(path))
    ]
    assert not offenders, (
        "G-Q049: `repositories/_unaudited.py` skips audit_log by design and may be imported only "
        f"by {ALLOWED}. Call a service that writes the audit row instead. Offenders: {offenders}"
    )


def test_the_detector_flags_an_import_outside_the_allowed_module() -> None:
    tree = ast.parse("from budget_planner.repositories._unaudited import set_next_due\n")
    assert _imports_unaudited(tree) == [1]
    tree = ast.parse("from budget_planner.repositories import _unaudited\n")
    assert _imports_unaudited(tree) == [1]
