"""G8 and the no-pass-through rule for services (T-Q285, ADR-0142 amendment 2026-11-22, ADR-0137).

Two rules, no allowlist:

* No module under ``services/`` binds a repository function to a module-level name
  (``list_all = accounts_repo.list_all``). A service entry point is a real ``def``.
* G8: a service function that calls two or more repository mutators runs them inside one
  ``db_transaction`` (``with db_transaction(conn):``). One mutator is atomic by itself (the
  repository writes the row and its audit row together).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture._ratchet import parse_file, repo_rel, src_files

READ_PREFIXES = (
    "find",
    "get",
    "list",
    "count",
    "sum",
    "latest",
    "any_",
    "hash_",
    "session_handle",
    "audit_view",
    "load",
    "owns",
    "require",
    "exists",
    "is_",
    "has_",
)
TRANSACTION_NAMES = frozenset({"db_transaction", "transaction"})


def _repo_aliases(tree: ast.Module) -> set[str]:
    """Names bound to a ``budget_planner.repositories`` module in this file."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "budget_planner.repositories"
        ):
            names.update(a.asname or a.name for a in node.names)
    return names


def pass_through_bindings(tree: ast.Module) -> list[int]:
    """Lines of module-level ``name = repo_module.function`` bindings."""
    aliases = _repo_aliases(tree)
    return [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id in aliases
    ]


def _mutator_calls(func: ast.AST, aliases: set[str]) -> int:
    count = 0
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases
            and not node.func.attr[:1].isupper()
            and not node.func.attr.startswith(READ_PREFIXES)
        ):
            count += 1
    return count


def _opens_transaction(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in TRANSACTION_NAMES
                ):
                    return True
    return False


def multi_mutator_without_transaction(tree: ast.Module) -> list[tuple[int, str]]:
    """``(line, function)`` of service functions with 2+ mutator calls and no transaction."""
    aliases = _repo_aliases(tree)
    return [
        (node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and _mutator_calls(node, aliases) >= 2
        and not _opens_transaction(node)
    ]


def _service_files() -> list[Path]:
    return src_files("services")


def test_no_service_binds_a_repository_function() -> None:
    offenders = [
        f"{repo_rel(p)}:{line}"
        for p in _service_files()
        for line in pass_through_bindings(parse_file(p))
    ]
    assert not offenders, (
        "ADR-0142 (T-Q285): a service entry point is a real `def` with typed arguments, not a "
        f"re-binding of a repository function. Offenders: {offenders}"
    )


def test_multi_mutator_services_use_one_transaction() -> None:
    offenders = [
        f"{repo_rel(p)}:{line} {name}"
        for p in _service_files()
        for line, name in multi_mutator_without_transaction(parse_file(p))
    ]
    assert not offenders, (
        "G8 (ADR-0137, T-Q285): a service calling two or more repository mutators must wrap them "
        f"in one `with db_transaction(conn):`. Offenders: {offenders}"
    )


def test_detectors_flag_a_binding_and_a_two_mutator_function() -> None:
    head = "from budget_planner.repositories import accounts as a_repo\n"
    assert pass_through_bindings(ast.parse(head + "x = a_repo.list_all\n")) == [2]
    two = ast.parse(head + "def f(c):\n    a_repo.create(c)\n    a_repo.update(c)\n")
    assert multi_mutator_without_transaction(two) == [(2, "f")]
    wrapped = ast.parse(
        head
        + "def f(c):\n    with db_transaction(c):\n"
        + "        a_repo.create(c)\n        a_repo.update(c)\n"
    )
    assert multi_mutator_without_transaction(wrapped) == []
