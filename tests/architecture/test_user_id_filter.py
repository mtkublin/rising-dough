"""T-D16 architecture test: every user-owned query is filtered by ``user_id``.

Backstops ADR-0022 (amended) + ADR-0061 §5. See ``_user_scoping.py`` for the
rule set. Scope: every module under ``repositories/``, ``services/`` and
``web/routers/`` — repositories own SQL, but any stray raw SQL in the
upper layers is held to the same bar.

Allowlist policy: an entry is ``(relative path, function name) -> reason``.
Only add one for a query that is *deliberately* cross-user (admin panel,
system sweeper, migration-adjacent maintenance) and say why in the reason.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.architecture._user_scoping import check_paths

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_ROOT = REPO_ROOT / "src" / "budget_planner"
SCANNED_DIRS = ("repositories", "services", "web/routers")

# (path relative to repo root, function name) -> justification.
SQL_ALLOWLIST: dict[tuple[str, str], str] = {}

# Repository modules that do not own user data, or whose lookups happen
# *before* the user is known (credential repos added by T-D02 resolve the
# user from an opaque session id / credential id).
NON_USER_SCOPED_REPOSITORIES: dict[str, str] = {
    "__init__.py": "package marker",
    "_shared.py": "transaction + audit helpers; no user-owned table access",
    "auth_users.py": "T-D02a: read-only lookups on `users` (the identity table, not user-owned)",
    "audit.py": "audit_log is not user-owned (actor columns are attribution)",
    "fx.py": "fx_rates is global reference data",
    "sessions.py": "T-D02: resolves the user from an opaque session id",
    "users.py": "T-D19: writes the `users` identity table (bootstrap, operator CLI, T-D17)",
    "webauthn.py": "T-D02: resolves the user from a credential id",
}

HARDCODED_USER_ID = re.compile(r"\buser_id\s*(?::\s*int\s*)?=\s*1\b")
ALLOWLIST_FILE = REPO_ROOT / ".user-id-filter-allowlist"


def _scanned_files() -> list[Path]:
    return [p for d in SCANNED_DIRS for p in sorted((PKG_ROOT / d).glob("*.py"))]


def test_every_user_owned_query_carries_user_id_predicate() -> None:
    violations = check_paths(_scanned_files(), REPO_ROOT, SQL_ALLOWLIST)
    assert not violations, "Unscoped SQL on user-owned tables:\n" + "\n".join(
        v.render() for v in violations
    )


def test_sql_allowlist_entries_point_at_real_functions() -> None:
    for (rel, func), reason in SQL_ALLOWLIST.items():
        assert reason.strip(), f"allowlist entry {rel}:{func} needs a reason"
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert func in names, f"stale allowlist entry {rel}:{func}"


def test_user_scoped_repository_functions_take_user_id_after_conn() -> None:
    offenders: list[str] = []
    for path in sorted((PKG_ROOT / "repositories").glob("*.py")):
        if path.name in NON_USER_SCOPED_REPOSITORIES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            params = [a.arg for a in node.args.posonlyargs + node.args.args]
            if params[:2] != ["conn", "user_id"]:
                offenders.append(f"{path.name}:{node.lineno} {node.name}{tuple(params)}")
    assert not offenders, "Repository functions must be (conn, user_id, ...):\n" + "\n".join(
        offenders
    )


def _allowlisted_paths() -> set[str]:
    entries: set[str] = set()
    for raw in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def test_no_hardcoded_user_id_in_application_code() -> None:
    allowed = _allowlisted_paths()
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for path in sorted(PKG_ROOT.rglob("*.py"))
        if str(path.relative_to(REPO_ROOT)) not in allowed
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if HARDCODED_USER_ID.search(line)
    ]
    assert not hits, "Hard-coded `user_id = 1` outside .user-id-filter-allowlist:\n" + "\n".join(
        hits
    )


def test_hardcoded_user_id_allowlist_has_no_stale_entries() -> None:
    for rel in _allowlisted_paths():
        path = REPO_ROOT / rel
        assert path.is_file(), f"stale allowlist entry {rel}"
        assert HARDCODED_USER_ID.search(path.read_text(encoding="utf-8")), (
            f"{rel} no longer hard-codes user_id = 1; drop it from the allowlist"
        )
