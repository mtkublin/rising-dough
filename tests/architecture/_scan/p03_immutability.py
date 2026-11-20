# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912, B023
"""P3 immutability. Rule (precise):

ALLOWED   a *local accumulator*: a name created in the function (``out = []; out.append(x)``,
          ``d = {}; d[k] = v``) that is returned or consumed there. Not inventoried.
VIOLATION in-place mutation of anything the function did not create:
  param-mutation:data       ``p.append/extend/update/...``, ``p[k] = v``, ``del p[k]``, ``p.attr = v`` rooted at a parameter
  param-mutation:framework  same, but the parameter is a framework object (request/response); framework requires
                            it, still listed so the guard allowlist is complete
  module-mutation           mutating call / subscript assignment on a module-level mutable name (shared state)
  setattr-bypass            ``object.__setattr__`` / ``setattr(`` (defeats frozen dataclasses)
Limitation: aliases (``x = p; x.append``) are not followed.
"""

from __future__ import annotations

import ast

from tests.architecture._scan._common import (
    dotted,
    layer,
    parse,
    py_files,
    rel,
    root_name,
    unparse,
    walk,
    write,
)

MUTATORS = {
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "popitem",
    "clear",
    "update",
    "setdefault",
    "add",
    "discard",
    "sort",
    "reverse",
    "difference_update",
    "intersection_update",
    "symmetric_difference_update",
    "appendleft",
    "extendleft",
    "popleft",
}
FRAMEWORK_PARAMS = {"request", "response", "websocket", "scope"}
MUT_CTORS = {"list", "dict", "set", "defaultdict", "deque", "Counter"}


def params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    a = fn.args
    singles = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    if a.vararg:
        singles.append(a.vararg)
    if a.kwarg:
        singles.append(a.kwarg)
    return {
        x.arg: (unparse(x.annotation, 40) if x.annotation else "")
        for x in singles
        if x.arg not in {"self", "cls"}
    }


def module_mutables(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for s in tree.body:
        if isinstance(s, ast.Assign | ast.AnnAssign) and s.value is not None:
            v = s.value
            if isinstance(v, ast.List | ast.Dict | ast.Set) or (
                isinstance(v, ast.Call) and dotted(v.func).split(".")[-1] in MUT_CTORS
            ):
                for t in s.targets if isinstance(s, ast.Assign) else [s.target]:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    return names


def main() -> None:
    rows: list[tuple[str, str, str]] = []
    for p in py_files():
        tree = parse(p)
        f = rel(p)
        lay = layer(p)
        mod_names = module_mutables(tree)
        for fn in [n for n in walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]:
            ps = params(fn)
            local_defs = {
                t.id
                for n in walk(fn)
                if isinstance(n, ast.Assign)
                for t in n.targets
                if isinstance(t, ast.Name)
            }

            def classify(
                root: str, ps: dict[str, str] = ps, local_defs: set[str] = local_defs
            ) -> tuple[str, str] | None:
                if root in ps:
                    fw = root in FRAMEWORK_PARAMS or "Request" in ps[root] or "Response" in ps[root]
                    return "param-mutation", "framework" if fw else "data"
                if root in mod_names and root not in local_defs:
                    return "module-mutation", "data"
                return None

            for n in walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    if n.func.attr in MUTATORS:
                        hit = classify(root_name(n.func.value))
                        if hit:
                            sub = f":{hit[1]}" if hit[0] == "param-mutation" else ""
                            rows.append(
                                (
                                    f"{f}:{n.lineno}",
                                    f"{hit[0]}{sub}",
                                    f"{lay} {fn.name}: {unparse(n)}",
                                )
                            )
                    if n.func.attr == "__setattr__" and dotted(n.func.value) == "object":
                        rows.append(
                            (f"{f}:{n.lineno}", "setattr-bypass", f"{fn.name}: {unparse(n)}")
                        )
                if isinstance(n, ast.Call) and dotted(n.func) == "setattr":
                    rows.append((f"{f}:{n.lineno}", "setattr-bypass", f"{fn.name}: {unparse(n)}"))
                targets: list[ast.AST] = []
                if isinstance(n, ast.Assign | ast.Delete):
                    targets = list(n.targets)
                elif isinstance(n, ast.AugAssign | ast.AnnAssign):
                    targets = [n.target]
                for t in targets:
                    if isinstance(t, ast.Subscript | ast.Attribute):
                        hit = classify(root_name(t))
                        if hit:
                            sub = f":{hit[1]}" if hit[0] == "param-mutation" else ""
                            rows.append(
                                (
                                    f"{f}:{n.lineno}",
                                    f"{hit[0]}{sub}",
                                    f"{lay} {fn.name}: {unparse(n)}",
                                )
                            )
    write(
        "p03-immutability",
        "P3 immutability. Script: repro/inventory/p03_immutability.py\n"
        "Local accumulators are allowed (not listed). Listed: in-place mutation of parameters, module-level mutable\n"
        "state, setattr bypass of frozen dataclasses.",
        rows,
    )
