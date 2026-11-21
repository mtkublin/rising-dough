"""P1 DRY / single source of truth.

Outputs
  p01-clones-ast       groups of functions whose bodies are structurally identical (type-2 clone: identifiers and constants
                       normalised; >= 4 statements or >= 8 lines). One row per member, group id in detail.
  p01-same-name        function names defined in >= 2 modules (private helpers or public), excluding dunder/route handlers
                       that only share conventional names (index, health) and ``main``.
  p01-pylint           parsed baseline/pylint-duplicate.txt (R0801 blocks), identical src tree at AUDIT_SHA 9fb18cb
  p01-jscpd            parsed baseline/jscpd.txt clones
Triage (real duplicate vs boilerplate) is a human column added in compliance-inventory.md, not in these files.
"""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict

from _common import ROOT, func_qualnames, layer, parse, py_files, rel, write

BASE = ROOT / "docs" / "plans" / "quality-audit" / "baseline"
IGNORE_NAMES = {"main", "index", "health", "__init__", "__repr__", "__str__", "__eq__", "__hash__", "lifespan", "dispatch", "create_app"}


class Norm(ast.NodeTransformer):
    def visit_Name(self, n: ast.Name) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Name(id="_", ctx=n.ctx), n)

    def visit_arg(self, n: ast.arg) -> ast.AST:  # noqa: N802
        return ast.arg(arg="_", annotation=None)

    def visit_Constant(self, n: ast.Constant) -> ast.AST:  # noqa: N802
        return ast.Constant(value=type(n.value).__name__)

    def visit_Attribute(self, n: ast.Attribute) -> ast.AST:  # noqa: N802
        self.generic_visit(n)
        return n


def body_hash(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]  # drop docstring
    mod = ast.Module(body=[Norm().visit(ast.parse(ast.unparse(b)).body[0]) for b in body], type_ignores=[])
    return hashlib.sha1(ast.dump(mod).encode()).hexdigest()[:10]


def p01_ast() -> None:
    groups: defaultdict[str, list[tuple[str, int, str, int]]] = defaultdict(list)
    names: defaultdict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for p in py_files():
        tree = parse(p)
        for q, fn in func_qualnames(tree):
            ln = (fn.end_lineno or fn.lineno) - fn.lineno + 1
            if fn.name not in IGNORE_NAMES and not fn.name.startswith("test_"):
                names[fn.name].append((rel(p), fn.lineno, layer(p)))
            if len(fn.body) >= 4 and ln >= 8:
                groups[body_hash(fn)].append((rel(p), fn.lineno, q, ln))
    rows = []
    gid = 0
    for h, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        gid += 1
        for f, ln, q, n in members:
            rows.append((f"{f}:{ln}", "clone-group", f"G{gid:02d} {q} ({n} lines) x{len(members)}"))
    write("p01-clones-ast", "P1 structurally identical function bodies (type-2 clones). Script: repro/inventory/p01_dry.py", rows)
    rows = []
    for nm, locs in sorted(names.items()):
        mods = {x[0] for x in locs}
        if len(mods) >= 2:
            for f, ln, lay in locs:
                rows.append((f"{f}:{ln}", "same-name", f"{nm} x{len(locs)} in {len(mods)} modules [{lay}]"))
    write("p01-same-name", "P1 function name defined in >= 2 modules (candidate parallel implementations). Script: repro/inventory/p01_dry.py", rows)


def p01_tools() -> None:
    rows = []
    txt = (BASE / "pylint-duplicate.txt").read_text().splitlines()
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in txt:
        m = re.match(r"==([\w.]+):\[(\d+):(\d+)\]", line)
        if m:
            cur.append(f"{m.group(1)}:{m.group(2)}-{m.group(3)}")
        elif cur and line.startswith("src/") or (cur and line.startswith("*************")):
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    # pylint prints each duplicate once per module pair; one row per block
    for i, b in enumerate(blocks, 1):
        mod, span = b[0].split(":")[0], b[0].split(":")[1]
        path = "src/" + mod.replace(".", "/") + ".py"
        rows.append((f"{path}:{span.split('-')[0]}", "pylint-R0801", f"P{i:02d} " + " <> ".join(b)))
    write("p01-pylint", "P1 pylint duplicate-code blocks (baseline/pylint-duplicate.txt; src identical to AUDIT_SHA).", rows)
    rows = []
    cur = []
    for line in (BASE / "jscpd.txt").read_text().splitlines():
        if line.startswith("Clone found"):
            if cur:
                rows.append(cur)
            cur = [line.split("(")[1].rstrip(")")]
        elif line.strip().startswith("-") or re.match(r"\s{3}\S", line):
            cur.append(line.strip().lstrip("- ").strip())
    if cur:
        rows.append(cur)
    out = []
    for i, c in enumerate(rows, 1):
        first = c[1]
        fname = first.split(" [")[0]
        out.append((f"web/{fname}:0", f"jscpd-{c[0]}", f"J{i:02d} " + " <> ".join(x for x in c[1:] if x)))
    write("p01-jscpd", "P1 jscpd clones over templates/css/js (baseline/jscpd.txt). Path relative to src/budget_planner/web/{templates,static}.", out)


if __name__ == "__main__":
    p01_ast()
    p01_tools()
