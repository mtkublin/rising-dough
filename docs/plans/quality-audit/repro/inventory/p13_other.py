"""P13 other stated principles (CLAUDE.md, requirements section 3, ~/.claude common rules, ADR-0061/0007).

Rules
  literal-user-id     int literal passed as user_id (kw or positional to a param named user_id), ``user_id = <int>`` default
  prod-db-path        string containing ``budget.sqlite`` in src
  silent-except       ``except ...: pass`` / ``continue`` / bare ``return`` with no log or raise (swallowed error)
  broad-except        ``except Exception`` / bare ``except`` (also listed when handled)
  assert-in-src       ``assert`` statement in src (stripped under -O; validation must raise)
  print-call          ``print(`` in src
  todo-marker         TODO / FIXME / XXX / HACK comments
  any-annotation      ``Any`` in a signature (ANN401)
  domain-literal      string literal equal to a domain constant (HX event names ``*-stale``, currency codes, ``Europe/Warsaw``,
                      direction/cadence values) outside its defining module (single-source-of-truth for literals)
  magic-number        int/float literal (other than 0, 1, 2, -1, 100 handled in P8) in a comparison or arithmetic outside UPPER_CASE
                      constant definitions (PLR2004-style)
  repeated-literal    same non-trivial string literal used >= 3 times in src (candidate constant); counts per literal
"""
from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict

from _common import dotted, enclosing_function_map, layer, parse, py_files, rel, src_lines, unparse, write

DOMAIN_STRINGS = re.compile(r"^(?:[a-z-]+-stale|settings-[a-z-]+-stale|PLN|EUR|USD|GBP|CHF|JPY|CZK|Europe/Warsaw)$")
DIRECTION_VALUES = {"income", "expense", "transit", "adjustment", "daily", "weekly", "monthly", "yearly", "weekdays"}
ALLOWED_NUM = {0, 1, 2, -1, 0.0, 1.0, 100, 100.0, 1000}


def user_id_positions() -> dict[str, set[int]]:
    """function simple name -> positional indexes of a parameter named user_id (names with conflicting positions are merged)."""
    pos: dict[str, set[int]] = {}
    for p in py_files():
        for n in ast.walk(parse(p)):
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                names = [a.arg for a in [*n.args.posonlyargs, *n.args.args] if a.arg != "self"]
                if "user_id" in names:
                    pos.setdefault(n.name, set()).add(names.index("user_id"))
    return pos


def main() -> None:
    uid_pos = user_id_positions()
    rows: list[tuple[str, str, str]] = []
    lit_count: defaultdict[str, list[str]] = defaultdict(list)
    for p in py_files():
        f = rel(p)
        lay = layer(p)
        tree = parse(p)
        enc = enclosing_function_map(tree)
        for i, line in enumerate(src_lines(p), 1):
            if re.search(r"#\s*(TODO|FIXME|XXX|HACK)\b", line):
                rows.append((f"{f}:{i}", "todo-marker", line.strip()[:90]))
        const_assign_lines: set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign | ast.AnnAssign):
                tg = n.targets if isinstance(n, ast.Assign) else [n.target]
                if all(isinstance(t, ast.Name) and t.id.isupper() or (isinstance(t, ast.Name) and t.id.startswith("_") and t.id.lstrip("_").isupper()) for t in tg):
                    for x in ast.walk(n):
                        if hasattr(x, "lineno"):
                            const_assign_lines.add(x.lineno)
        for n in ast.walk(tree):
            ln = getattr(n, "lineno", 0)
            where = f"{f}:{ln}"
            fn = enc.get(id(n), "<module>")
            if isinstance(n, ast.Call):
                for kw in n.keywords:
                    if kw.arg == "user_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                        rows.append((where, "literal-user-id", f"[{lay}] {fn}: {unparse(n, 80)}"))
                callee = dotted(n.func).split(".")[-1] if dotted(n.func) else ""
                for idx in (uid_pos.get(callee, ()) if callee not in {"get", "pop", "setdefault"} else ()):
                    if idx < len(n.args) and isinstance(n.args[idx], ast.Constant) and isinstance(n.args[idx].value, int) and not isinstance(n.args[idx].value, bool):
                        rows.append((where, "literal-user-id", f"[{lay}] {fn}: positional {unparse(n, 80)}"))
                if dotted(n.func) == "print":
                    rows.append((where, "print-call", f"[{lay}] {fn}"))
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                a = n.args
                allargs = [*a.posonlyargs, *a.args, *a.kwonlyargs]
                defaults = [None] * (len(a.posonlyargs + a.args) - len(a.defaults)) + list(a.defaults) + list(a.kw_defaults)
                for arg, dflt in zip(allargs, defaults, strict=False):
                    if arg.arg == "user_id" and isinstance(dflt, ast.Constant) and isinstance(dflt.value, int):
                        rows.append((where, "literal-user-id", f"[{lay}] default {n.name}(user_id={dflt.value})"))
                    if arg.annotation is not None and re.search(r"\bAny\b", unparse(arg.annotation)):
                        rows.append((f"{f}:{arg.lineno}", "any-annotation", f"[{lay}] {n.name}({arg.arg}: {unparse(arg.annotation, 30)})"))
                if n.returns is not None and re.search(r"\bAny\b", unparse(n.returns)):
                    rows.append((where, "any-annotation", f"[{lay}] {n.name}() -> {unparse(n.returns, 30)}"))
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "user_id" for t in n.targets) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, int):
                rows.append((where, "literal-user-id", f"[{lay}] {fn}: {unparse(n)}"))
            if isinstance(n, ast.Assert):
                rows.append((where, "assert-in-src", f"[{lay}] {fn}: {unparse(n, 70)}"))
            if isinstance(n, ast.ExceptHandler):
                t = unparse(n.type) if n.type else "<bare>"
                broad = t in {"Exception", "BaseException", "<bare>"}
                body_calls = {dotted(c.func).split(".")[-1] for b in n.body for c in ast.walk(b) if isinstance(c, ast.Call)}
                raises = any(isinstance(c, ast.Raise) for b in n.body for c in ast.walk(b))
                logs = bool(body_calls & {"debug", "info", "warning", "error", "exception", "critical", "log"})
                if broad:
                    rows.append((where, "broad-except", f"[{lay}] {fn}: except {t}"))
                trivial = all(isinstance(b, ast.Pass | ast.Continue) or (isinstance(b, ast.Return) and (b.value is None or isinstance(b.value, ast.Constant))) for b in n.body)
                if trivial and not raises and not logs:
                    rows.append((where, "silent-except", f"[{lay}] {fn}: except {t}: {unparse(n.body[0], 30)}"))
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                v = n.value
                if "budget.sqlite" in v:
                    rows.append((where, "prod-db-path", f"[{lay}] {v[:60]}"))
                if DOMAIN_STRINGS.match(v) or v in DIRECTION_VALUES:
                    if ln not in const_assign_lines and fn != "<module>" or (ln not in const_assign_lines):
                        rows.append((where, "domain-literal", f"[{lay}] {fn}: {v!r}"))
                if len(v) >= 4 and re.fullmatch(r"[\w .:/#%-]+", v) and ln not in const_assign_lines and not v.isdigit():
                    lit_count[v].append(where)
            if isinstance(n, ast.Compare) and ln not in const_assign_lines:
                for c in [n.left, *n.comparators]:
                    if isinstance(c, ast.Constant) and isinstance(c.value, int | float) and not isinstance(c.value, bool) and c.value not in ALLOWED_NUM:
                        rows.append((where, "magic-number", f"[{lay}] {fn}: {unparse(n, 70)}"))
            if isinstance(n, ast.BinOp) and ln not in const_assign_lines and isinstance(n.op, ast.Mult | ast.Div | ast.FloorDiv | ast.Mod | ast.Add | ast.Sub):
                for c in (n.left, n.right):
                    if isinstance(c, ast.Constant) and isinstance(c.value, int | float) and not isinstance(c.value, bool) and c.value not in ALLOWED_NUM:
                        rows.append((where, "magic-number", f"[{lay}] {fn}: {unparse(n, 70)}"))
    docstr = re.compile(r"^[A-Z].*\s")  # prose-looking strings are docstrings/messages, not constants
    all_rep: list[tuple[str, str, str]] = []
    for v, locs in lit_count.items():
        nfiles = len({x.split(':')[0] for x in locs})
        if len(locs) >= 3 and not docstr.match(v) and " " not in v.strip():
            row = (locs[0], "repeated-literal", f"{v!r} x{len(locs)} (files: {nfiles})")
            all_rep.append(row)
            if nfiles >= 2 and re.search(r"[-/:.]|^[A-Z]{3,}$", v):
                rows.append(row)
    write("p13-repeated-literals-all", "P13 every string literal used >= 3 times (mostly column/field names; noisy, reference only)", all_rep)
    write(
        "p13-other",
        "P13 other principles. Script: repro/inventory/p13_other.py\n"
        "Rules: literal-user-id, prod-db-path, silent-except, broad-except, assert-in-src, print-call, todo-marker, any-annotation,\n"
        "domain-literal (HX event/currency/tz/direction literal outside a constant), magic-number, repeated-literal.",
        rows,
    )


if __name__ == "__main__":
    main()
