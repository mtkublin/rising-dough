# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G6: banned-copy and banned-primitive ratchet (ADR-0130 section 3).

* function names matching a registry row's ``banned`` patterns (``canonical_modules.toml``) must not be defined
  outside that row's canonical module;
* money rounding primitives (``Decimal("100")``, ``.quantize(``, ``ROUND_HALF_*``) live only in ``domain/money.py``.

Arithmetic ``/ 100`` and ``* 100``, ``round(`` and amount parsers are covered by G27 (``test_money_scope.py``).
Allowlist: ``allowlists/banned_patterns.toml``.
"""

from __future__ import annotations

import ast
import fnmatch
from pathlib import Path
from typing import Any

from tests.architecture._ratchet import (
    SRC_ROOT,
    Violation,
    assert_ratchet,
    parse_file,
    repo_rel,
    src_files,
)
from tests.architecture.test_canonical_modules import load_registry

GUARD = "banned_patterns"
HEADER = "G6 banned_patterns: copies of canonical-module functions and money rounding primitives outside domain/money.py."
SCOPE = ("services", "web", "repositories")
MONEY_HOME = "domain/money.py"
TEACH = (
    "G6 banned copies: call the canonical function listed in canonical_modules.toml (CLAUDE.md Canonical modules) "
    "instead of defining another one. `target` rows are not yet extracted: call the nearest listed function and note it "
    "in the report (ADR-0130 section 3; Q-002, Q-003, Q-007, Q-008, Q-009, Q-010, Q-023, Q-036, Q-076)."
)


def _rel_to_pkg(path: Path) -> str:
    return path.resolve().relative_to(SRC_ROOT).as_posix()


def scan_tree(
    tree: ast.Module, rel: str, shown: str, registry: list[dict[str, Any]]
) -> list[Violation]:
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for row in registry:
                if row["module"] != rel and any(
                    fnmatch.fnmatchcase(node.name, p) for p in row["banned"]
                ):
                    out.append(
                        Violation(
                            shown, node.lineno, "banned-name", f"def {node.name} ({row['concept']})"
                        )
                    )
                    break
        if rel == MONEY_HOME:
            continue
        if isinstance(node, ast.Name) and node.id.startswith("ROUND_HALF"):
            out.append(Violation(shown, node.lineno, "money-primitive", node.id))
        elif isinstance(node, ast.Attribute) and node.attr == "quantize":
            out.append(Violation(shown, node.lineno, "money-primitive", ".quantize"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Decimal"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value) == "100"
        ):
            out.append(Violation(shown, node.lineno, "money-primitive", 'Decimal("100")'))
    return out


def collect() -> list[Violation]:
    registry = load_registry()
    found: list[Violation] = []
    for path in src_files(*SCOPE):
        found += scan_tree(parse_file(path), _rel_to_pkg(path), repo_rel(path), registry)
    return found


def meta(v: Violation) -> tuple[str, str, str, str]:
    if v.rule == "money-primitive":
        return "entry", "Q-076", "E11", ""
    for row in load_registry():
        if f"({row['concept']})" in v.detail:
            return "entry", str(row["finding"]), str(row["epic"]), ""
    return "entry", "Q-007", "E01", ""


def test_banned_patterns_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_banned_patterns_detect_fixture_violations() -> None:
    source = (
        "from decimal import Decimal, ROUND_HALF_UP\n"
        "def _convert_native_to_base(x):\n"
        "    return (Decimal(x) * Decimal('100')).quantize(Decimal(1), rounding=ROUND_HALF_UP)\n"
    )
    hits = scan_tree(
        ast.parse(source), "services/forecast.py", "services/forecast.py", load_registry()
    )
    assert {v.rule for v in hits} == {"banned-name", "money-primitive"}
    canonical = scan_tree(ast.parse(source), "services/fx.py", "services/fx.py", load_registry())
    assert not any(v.rule == "banned-name" for v in canonical)
