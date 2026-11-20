# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912, SIM223, F841
"""P9 layering/imports, P10 signatures/size, P11 suppressions.

P9 outputs
  p09-layering        direct first-party imports that break a contract (any nesting depth, TYPE_CHECKING excluded) + SCCs
  p09-lazy-imports    every import inside a function body (PLC0415) and every non-top-of-file import (E402)
P10 outputs
  p10-size            files >400 / >800 lines, functions >50 lines, functions with cc >= 11 (own McCabe approximation;
                      baseline/radon-cc.txt is the authoritative C+ list for the identical AUDIT_SHA tree),
                      nesting depth > 4, parameter count > 5 (PLR0913 is ignored globally) and positional > 5 (PLR0917)
P11 output
  p11-suppressions    every noqa / type: ignore / nosec / pragma: no cover / pylint / ruff: noqa / mypy: with reason flag,
                      plus pyproject per-file-ignores and coverage exclude_lines
"""

from __future__ import annotations

import ast
import re
import tomllib

from tests.architecture._scan._common import (
    PKG,
    ROOT,
    layer,
    module_index,
    module_name,
    parse,
    py_files,
    rel,
    src_lines,
    walk,
    write,
)

CONTRACTS = [
    ("routers-not-repositories", "web.routers", "budget_planner.repositories"),
    ("web-not-db", "web", "budget_planner.db"),
    ("domain-pure-services", "domain", "budget_planner.services"),
    ("domain-pure-repositories", "domain", "budget_planner.repositories"),
    ("domain-pure-web", "domain", "budget_planner.web"),
    ("domain-pure-db", "domain", "budget_planner.db"),
    ("domain-pure-adapters", "domain", "budget_planner.adapters"),
    ("repositories-not-services", "repositories", "budget_planner.services"),
    ("repositories-not-web", "repositories", "budget_planner.web"),
    ("services-not-web", "services", "budget_planner.web"),
    ("services-not-db", "services", "budget_planner.db"),  # info contract (not in prevention.md G1)
    ("web-vm-not-repositories", "web", "budget_planner.repositories"),  # info contract
    ("adapters-not-web", "adapters", "budget_planner.web"),
]


def in_layer(lay: str, want: str) -> bool:
    if want == "web":
        return lay in {"web", "web.routers", "web.middleware"}
    return lay == want


def is_type_checking(node: ast.AST) -> bool:
    return isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)


def walk_imports(tree: ast.Module):
    """Yield (node, in_function, under_type_checking)."""

    def visit(node: ast.AST, in_fn: bool, tc: bool):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.Import | ast.ImportFrom):
                yield ch, in_fn, tc
            elif isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef):
                yield from visit(ch, True, tc)
            else:
                yield from visit(ch, in_fn, tc or is_type_checking(ch))

    yield from visit(tree, False, False)


def targets(n: ast.Import | ast.ImportFrom, mod: str, is_pkg: bool, known: set[str]) -> list[str]:
    out: list[str] = []
    if isinstance(n, ast.Import):
        return [a.name for a in n.names if a.name.startswith(PKG)]
    base = n.module or ""
    if n.level:
        pkg = mod.split(".") if is_pkg else mod.split(".")[:-1]
        pkg = pkg[: len(pkg) - (n.level - 1)]
        base = ".".join(pkg + ([n.module] if n.module else []))
    if not base.startswith(PKG):
        return []
    for a in n.names:
        full = f"{base}.{a.name}"
        out.append(full if full in known else base)
    return out


def scc(graph: dict[str, set[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    res: list[list[str]] = []
    counter = [0]

    def strong(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                res.append(sorted(comp))

    for v in sorted(graph):
        if v not in index:
            strong(v)
    return res


def p09() -> None:
    known = module_index()
    layering: list[tuple[str, str, str]] = []
    lazy: list[tuple[str, str, str]] = []
    graph: dict[str, set[str]] = {}
    for p in py_files():
        mod = module_name(p)
        lay = layer(p)
        tree = parse(p)
        is_pkg = p.name == "__init__.py"
        lines = src_lines(p)
        first_code_done = False
        for n, in_fn, tc in walk_imports(tree):
            tg = targets(n, mod, is_pkg, known)
            if in_fn and not tc:
                note = "noqa" if "noqa" in lines[n.lineno - 1] else "no-noqa"
                lazy.append(
                    (
                        f"{rel(p)}:{n.lineno}",
                        "lazy-import",
                        f"[{lay}] {', '.join(tg) or ast.unparse(n)} ({note})",
                    )
                )
            if not tc and tg:
                for t in tg:
                    graph.setdefault(mod, set()).add(t)
                for name, src_l, dst in CONTRACTS:
                    if in_layer(lay, src_l) and any(
                        t == dst or t.startswith(dst + ".") for t in tg
                    ):
                        for t in tg:
                            if t == dst or t.startswith(dst + "."):
                                if name == "web-vm-not-repositories" and lay != "web":
                                    continue
                                if name == "web-not-db" and lay == "web.routers" and False:
                                    continue
                                kind = "fn-level" if in_fn else "top-level"
                                info = (
                                    "info"
                                    if name in {"services-not-db", "web-vm-not-repositories"}
                                    else "contract"
                                )
                                layering.append(
                                    (
                                        f"{rel(p)}:{n.lineno}",
                                        f"{info}:{name}",
                                        f"{mod} -> {t} ({kind})",
                                    )
                                )
        # E402: imports after first non-import, non-docstring top-level statement
        seen_code = False
        for s in tree.body:
            if isinstance(s, ast.Import | ast.ImportFrom):
                if seen_code:
                    lazy.append(
                        (
                            f"{rel(p)}:{s.lineno}",
                            "late-import-E402",
                            f"[{lay}] {ast.unparse(s)[:70]}",
                        )
                    )
            elif not (
                isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant)
            ) and not isinstance(s, ast.If):
                seen_code = True
    # SCC over module graph (all imports incl. function-level)
    pkgs_graph = {m: {t for t in ts if t in known} for m, ts in graph.items()}
    for comp in scc(pkgs_graph):
        for m in comp:
            layering.append((f"{m.replace('.', '/')}.py:0", "cycle", "SCC: " + " <-> ".join(comp)))
    write(
        "p09-layering",
        "P9 layering. Script: repro/inventory/p09_p10_p11_imports_size_suppress.py\n"
        "contract:* = in prevention.md G1 set; info:* = extra contracts (services->db, web view-model -> repositories).\n"
        "Direct first-party imports at any depth (TYPE_CHECKING excluded). cycle = strongly connected component of the module graph.",
        layering,
    )
    write(
        "p09-lazy-imports",
        "P9 imports inside functions (PLC0415) and imports after code (E402). (noqa)=has a noqa on the line.",
        lazy,
    )


def cc(fn: ast.AST) -> int:
    n = 1
    for x in walk(fn):
        if isinstance(
            x,
            ast.If
            | ast.For
            | ast.AsyncFor
            | ast.While
            | ast.IfExp
            | ast.ExceptHandler
            | ast.Assert
            | ast.comprehension,
        ):
            n += 1
        elif isinstance(x, ast.BoolOp):
            n += len(x.values) - 1
    return n


def depth(node: ast.AST, d: int = 0) -> int:
    m = d
    for ch in ast.iter_child_nodes(node):
        nd = (
            d + 1
            if isinstance(
                ch, ast.If | ast.For | ast.While | ast.Try | ast.With | ast.AsyncFor | ast.AsyncWith
            )
            else d
        )
        if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        m = max(m, depth(ch, nd))
    return m


def p10() -> None:
    rows: list[tuple[str, str, str]] = []
    for p in py_files():
        tree = parse(p)
        f = rel(p)
        n_lines = len(src_lines(p))
        if n_lines > 800:
            rows.append((f"{f}:1", "file>800", f"{n_lines} lines"))
        elif n_lines > 400:
            rows.append((f"{f}:1", "file>400", f"{n_lines} lines"))
        for q, fn in [
            (x.name, x) for x in walk(tree) if isinstance(x, ast.FunctionDef | ast.AsyncFunctionDef)
        ]:
            ln = (fn.end_lineno or fn.lineno) - fn.lineno + 1
            if ln > 50:
                rows.append((f"{f}:{fn.lineno}", "func>50", f"{q} {ln} lines"))
            c = cc(fn)
            if c >= 11:
                rows.append((f"{f}:{fn.lineno}", "cc>=11", f"{q} cc~{c}"))
            dp = depth(fn)
            if dp > 4:
                rows.append((f"{f}:{fn.lineno}", "nesting>4", f"{q} depth {dp}"))
            a = fn.args
            pos = [x.arg for x in [*a.posonlyargs, *a.args] if x.arg not in {"self", "cls"}]
            allp = pos + [x.arg for x in a.kwonlyargs]
            if len(pos) > 5:
                rows.append((f"{f}:{fn.lineno}", "positional>5", f"{q} {len(pos)} positional"))
            if len(allp) > 5:
                rows.append((f"{f}:{fn.lineno}", "params>5", f"{q} {len(allp)} params"))
    write(
        "p10-size",
        "P10 size/signatures. Script: repro/inventory/p09_p10_p11_imports_size_suppress.py\n"
        "file>400 (warn), file>800, func>50 lines, cc>=11 (own approximation; radon baseline authoritative), nesting>4,\n"
        "positional>5 (PLR0917), params>5 (PLR0913, ignored globally).",
        rows,
    )


SUPP = re.compile(
    r"#\s*(noqa|type:\s*ignore|nosec|pragma:\s*no cover|pylint:|ruff:\s*noqa|mypy:|fmt:\s*(off|skip)|isort:)(.*)$",
    re.I,
)


def p11() -> None:
    rows: list[tuple[str, str, str]] = []
    for p in py_files():
        f = rel(p)
        lines = src_lines(p)
        for i, line in enumerate(lines, 1):
            m = SUPP.search(line)
            if not m or (line.lstrip().startswith(('"', "'")) and "#" not in line.split('"')[0]):
                continue
            kind = re.sub(r"\s+", " ", m.group(1).lower())
            rest = m.group(3).strip()
            codes = ""
            reason = ""
            if kind == "noqa":
                mm = re.match(r":\s*([A-Z0-9, ]+?)(?:\s+[-#—:]+\s*|\s{2,}|$)(.*)", rest)
                if mm:
                    codes, reason = mm.group(1).strip(), mm.group(2).strip()
                else:
                    codes = rest
                if not codes:
                    codes = "BLANKET"
            elif kind.startswith("type:"):
                mm = re.match(r"(\[[^\]]*\])?\s*(?:[-#—]+\s*)?(.*)", rest)
                codes, reason = (mm.group(1) or "BLANKET"), (mm.group(2) or "").strip()
            else:
                reason = re.sub(r"^[-#—:\s]+", "", rest)
            if "nosec" in line and kind != "nosec":
                rows.append(
                    (
                        f"{f}:{i}",
                        "suppress:nosec",
                        "reason-same-line=" + ("yes" if "—" in line.split("nosec")[0] else "NO"),
                    )
                )
            above = lines[i - 2].strip() if i >= 2 else ""
            has_above = "yes" if above.startswith("#") else "no"
            rows.append(
                (
                    f"{f}:{i}",
                    f"suppress:{kind}",
                    f"{codes or '-'} | reason-same-line={'yes' if reason else 'NO'} | comment-above={has_above}",
                )
            )
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    for pat, codes in (
        cfg.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {}) or {}
    ).items():
        rows.append(("pyproject.toml:0", "config:per-file-ignore", f"{pat} -> {','.join(codes)}"))
    for code in cfg.get("tool", {}).get("ruff", {}).get("lint", {}).get("ignore", []) or []:
        rows.append(("pyproject.toml:0", "config:global-ruff-ignore", code))
    for x in (
        cfg.get("tool", {}).get("coverage", {}).get("report", {}).get("exclude_lines", []) or []
    ):
        rows.append(("pyproject.toml:0", "config:coverage-exclude", x))
    for o in cfg.get("tool", {}).get("mypy", {}).get("overrides", []) or []:
        rows.append(("pyproject.toml:0", "config:mypy-override", str(o)[:120]))
    write(
        "p11-suppressions",
        "P11 suppressions. Script: repro/inventory/p09_p10_p11_imports_size_suppress.py\n"
        "reason-same-line = text after the code list on the comment (a reason in a comment ABOVE does not count, per G4).\n"
        "config:* rows = pyproject.toml suppressions (per-file-ignores, global ignores, coverage excludes, mypy overrides).",
        rows,
    )
