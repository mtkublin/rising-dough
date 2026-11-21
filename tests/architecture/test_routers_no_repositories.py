"""T-Q241 (ADR-0142): routers reach persistence only through services.

No allowlist: a router importing ``budget_planner.repositories`` (or a submodule, or a name from
it) fails. Complements the import-linter contract "routers do not import repositories".
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[2] / "src" / "budget_planner" / "web" / "routers"
FORBIDDEN = "budget_planner.repositories"


def _offending_imports(source: str) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(FORBIDDEN):
            hits.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            hits.extend(f"import {a.name}" for a in node.names if a.name.startswith(FORBIDDEN))
    return hits


def test_routers_do_not_import_repositories() -> None:
    offenders = {
        p.name: hits
        for p in sorted(ROUTERS.glob("*.py"))
        if (hits := _offending_imports(p.read_text()))
    }
    assert not offenders, f"routers must call services, never repositories (ADR-0142): {offenders}"


def test_scanner_detects_repository_import() -> None:
    assert _offending_imports("from budget_planner.repositories import accounts\n")
    assert _offending_imports("from budget_planner.repositories.sessions import X\n")
    assert _offending_imports("import budget_planner.repositories.fx\n")
    assert not _offending_imports("from budget_planner.services import accounts\n")
