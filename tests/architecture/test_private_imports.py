# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G30: no cross-module use of another module's private (``_name``) symbols (ADR-0130, T-Q16 dry run V2).

Flagged inside ``src/budget_planner``:

* ``private-import``: ``from budget_planner.x import _name`` (absolute or relative);
* ``private-attr``: ``mod._name`` where ``mod`` was imported as a module from the package.

Dunders and ``__future__`` are ignored; tests are out of scope. Ruff SLF001 does not cover ``from x import _name``.
Allowlist: ``allowlists/private_imports.toml`` (exact ratchet, burn-down to zero).
"""

from __future__ import annotations

import ast

from tests.architecture._ratchet import (
    Violation,
    assert_ratchet,
    parse_file,
    repo_rel,
    src_files,
)

GUARD = "private_imports"
HEADER = "G30 private_imports: use of another module's private _name symbols (cross-module private import or attribute)."
TEACH = (
    "G30 private use: never import or reference another module's `_private` name. Call its public function; "
    "if none exists, promote the helper to a public name in its owning module (or the canonical module in "
    "CLAUDE.md Canonical modules) and migrate every copy in the same change, or do the registered migration task."
)


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _is_package(module: str | None, level: int) -> bool:
    return level > 0 or module == "budget_planner" or (module or "").startswith("budget_planner.")


def scan_tree(tree: ast.Module, shown: str) -> list[Violation]:
    out: list[Violation] = []
    module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            if not _is_package(node.module, node.level):
                continue
            for alias in node.names:
                if _is_private(alias.name):
                    out.append(
                        Violation(
                            shown, node.lineno, "private-import", f"{node.module}.{alias.name}"
                        )
                    )
                else:
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("budget_planner") and alias.asname:
                    module_aliases.add(alias.asname)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in module_aliases
            and _is_private(node.attr)
        ):
            out.append(
                Violation(shown, node.lineno, "private-attr", f"{node.value.id}.{node.attr}")
            )
    return out


def collect() -> list[Violation]:
    found: list[Violation] = []
    for path in src_files():
        found += scan_tree(parse_file(path), repo_rel(path))
    return found


def test_private_imports_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_private_imports_detect_fixture_violations() -> None:
    source = (
        "from __future__ import annotations\n"
        "from budget_planner.services.budget import _month_range, month_summary\n"
        "from budget_planner.services import forecast\n"
        "from .analytics import _month_bounds\n"
        "from other_lib import _fine\n"
        "x = forecast._month_bounds\n"
        "y = forecast.__name__\n"
    )
    hits = scan_tree(ast.parse(source), "services/x.py")
    assert sorted((v.rule, v.detail) for v in hits) == [
        ("private-attr", "forecast._month_bounds"),
        ("private-import", "analytics._month_bounds"),
        ("private-import", "budget_planner.services.budget._month_range"),
    ]
