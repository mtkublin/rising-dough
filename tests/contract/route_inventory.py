"""Route inventory for the contract layer (ADR-0106 section 1, T-UT03).

``collect_routes`` flattens the FastAPI route table (including routers added
through ``include_router``) into frozen ``RouteInfo`` rows. ``check_coverage``
is a pure function over (routes, covered, allowlist) so it can be unit-tested.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from budget_planner.web.middleware.auth import EXEMPT_PATHS, STATIC_PREFIX

KEY_PATTERN: Final = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|MOUNT) /\S*$")
_ROUTER_PREFIX: Final = "budget_planner.web.routers."
_FRAGMENT_NAMES: Final = frozenset(
    {
        "limit_preview",
        "recently_deleted_panel",
        "last_checked",
        "drawer",
        "close",
        "add_entry_overlay",
    }
)


@dataclass(frozen=True, slots=True)
class RouteInfo:
    method: str
    path: str
    router: str
    handler: str
    kind: str  # page | fragment | action
    auth: str  # public | session | session+recent-auth | admin

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


def _walk(routes: Iterable[Any]) -> Iterator[Any]:
    """Flatten included routers (FastAPI >= 0.16x wraps them lazily)."""
    for route in routes:
        effective = getattr(route, "effective_candidates", None)
        if effective is not None:
            yield from _walk(effective())
        else:
            yield route


def _kind(method: str, module: str, name: str) -> str:
    if method != "GET":
        return "action"
    if name.endswith("_fragment") or name in _FRAGMENT_NAMES:
        return "fragment"
    if name.endswith("_form") and module != "auth":
        return "fragment"
    if name == "export":
        return "action"
    return "page"


def _auth(path: str, module: str, route: Any) -> str:
    if path in EXEMPT_PATHS or path.startswith(STATIC_PREFIX):
        return "public"
    deps = [getattr(d, "dependency", None) for d in getattr(route, "dependencies", [])]
    if any(getattr(d, "__name__", "") == "require_recent_auth" for d in deps):
        return "session+recent-auth"
    return "admin" if module == "settings_users" else "session"


def collect_routes(app: Any) -> tuple[RouteInfo, ...]:
    """Every (method, path) on ``app``; HEAD aliases skipped, mounts as MOUNT."""
    rows: list[RouteInfo] = []
    for route in _walk(app.routes):
        path = str(route.path)
        endpoint = getattr(route, "endpoint", None)
        methods = getattr(route, "methods", None)
        if endpoint is None or not methods:
            rows.append(RouteInfo("MOUNT", path, "framework", "-", "action", "public"))
            continue
        module = str(endpoint.__module__)
        short = (
            module.removeprefix(_ROUTER_PREFIX)
            if module.startswith(_ROUTER_PREFIX)
            else "framework"
        )
        for method in sorted(methods - {"HEAD"}):
            rows.append(
                RouteInfo(
                    method,
                    path,
                    short,
                    endpoint.__name__,
                    _kind(method, short, endpoint.__name__),
                    _auth(path, short, route),
                )
            )
    return tuple(rows)


def _is_covers_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "covers") or (
        isinstance(func, ast.Attribute) and func.attr == "covers"
    )


def collect_covered(root: Path, *, skip: frozenset[str] = frozenset()) -> frozenset[str]:
    """Static scan of every ``covers("<METHOD> <path>")`` call under ``root``.

    AST based, so it is independent of pytest collection, xdist and test
    selection.
    """
    keys: set[str] = set()
    for file in sorted(root.rglob("*.py")):
        if file.name in skip:
            continue
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if _is_covers_call(node):
                assert isinstance(node, ast.Call)
                keys.update(
                    a.value
                    for a in node.args
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                )
    return frozenset(keys)


def check_coverage(
    routes: frozenset[str],
    covered: frozenset[str],
    allowlist: Mapping[str, str],
) -> tuple[str, ...]:
    """Return human-readable problems; empty means the inventory is consistent."""
    problems: list[str] = []
    problems += [
        f"uncovered route (add @covers or allowlist): {k}"
        for k in sorted(routes - covered - allowlist.keys())
    ]
    problems += [
        f"stale allowlist entry (route gone): {k}" for k in sorted(allowlist.keys() - routes)
    ]
    problems += [
        f"allowlisted but covered (remove the allowlist entry): {k}"
        for k in sorted(covered & allowlist.keys())
    ]
    problems += [f"@covers names unknown route: {k}" for k in sorted(covered - routes)]
    problems += [
        f"malformed key: {k}" for k in sorted(routes | covered) if not KEY_PATTERN.match(k)
    ]
    return tuple(problems)
