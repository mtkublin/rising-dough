"""Generate the Track D authz table rows from the live app + AST (T-Q07).

For each route: method, path, id-like path params, first source line where the current user id is
handed to a repository/service call (`user_id`, `user.id`, `admin.id`), and dependency hints
(current_user_id / current_user / current_admin / require_recent_auth).
Run: BUDGET_DATABASE_URL=sqlite:////tmp/audit-D.sqlite uv run python docs/plans/quality-audit/repro/D/route_table.py
"""

from __future__ import annotations

import ast
import inspect

from fastapi.routing import APIRoute

from budget_planner.web.app import app


def walk(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from walk(r.original_router.routes)


def scoping_lines(fn) -> list[int]:
    src, start = inspect.getsourcelines(fn)
    tree = ast.parse("".join(src).lstrip() if src[0].startswith(" ") is False else "".join(src))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            names = [a for a in list(node.args) + [k.value for k in node.keywords]]
            for a in names:
                seg = ast.unparse(a)
                if seg in ("user_id", "user.id", "admin.id", "1") and seg != "1" or seg == "1" and False:
                    out.append(start + node.lineno - 1)
                    break
    return sorted(set(out))


EXEMPT = {"/health", "/ready", "/health/replication", "/auth/login", "/auth/login/begin", "/auth/login/finish"}
rows = []
for r in walk(app.routes):
    ep = r.endpoint
    deps = [d.call.__name__ for d in r.dependant.dependencies if getattr(d, "call", None)]
    src = inspect.getsourcefile(ep) or ""
    if "site-packages" in src:
        deps = ["(fastapi builtin)"]
    path_ids = [p.name for p in r.dependant.path_params]
    lines = scoping_lines(ep) if "site-packages" not in src else []
    rows.append(
        (
            sorted(r.methods)[0],
            r.path,
            src.split("src/")[-1] + f":{ep.__code__.co_firstlineno}",
            ",".join(path_ids),
            "no" if r.path in EXEMPT else "yes",
            ",".join(sorted(set(deps))),
            ",".join(map(str, lines)),
        )
    )
for row in sorted(rows, key=lambda x: (x[1], x[0])):
    print(" | ".join(row))
print(len(rows), "api routes (+ /static mount)")
