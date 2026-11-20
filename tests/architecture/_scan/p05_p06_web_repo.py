# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912
"""P5 thin web / fat services and P6 repository discipline.

P5 output ``p05-thin-web``: one row per function in ``web/routers/*.py`` (handlers AND helpers) that carries a
business-logic signal. Detail column: ``kind lines cc | signals``.
  R repo call (call resolved into budget_planner.repositories.*)        S SQL / conn.execute
  A arithmetic on non-string operands (- * / // % ** and + without str)  G aggregation (sum/min/max/sorted/Counter/groupby/loop-with-accumulator)
  D domain branch (comparison against a Direction/Cadence/Kind enum member or literal on .direction/.kind/.cadence/.status)
  T txn/transaction control (conn.commit/rollback, transaction())       P private helper that is not a route (logic outside handler)
  F FX / money conversion call (convert/to_minor/format_money/parse_amount)  C date construction/arith (date(, timedelta, replace(day=))
A function is *thin* when it has none of R S A G D T F C.
P6 outputs:
  p06-sql-outside-repos   SQL strings / execute calls outside repositories/ (db/ bootstrap tagged)
  p06-unaudited-mutations mutating SQL in repositories/ not under mutate()/write_audit()
  p06-read-filters        SELECTs touching soft-delete / user-owned tables without deleted_at / user_id in the function
"""

from __future__ import annotations

import ast
import re
import tomllib  # noqa: F401  (kept for parity with other scripts)

from tests.architecture._scan._common import (
    ROOT,
    dotted,
    enclosing_function_map,
    func_qualnames,
    layer,
    module_index,
    module_name,
    parse,
    py_files,
    rel,
    resolve_call,
    resolve_imports,
    unparse,
    walk,
    write,
)

SQL_RE = re.compile(
    r"^\s*(SELECT\b.*\bFROM\b|INSERT\s+(OR\s+\w+\s+)?INTO\b|UPDATE\s+\S+\s+SET\b|DELETE\s+FROM\b|PRAGMA\s+\w|VACUUM\b"
    r"|WITH\s+\w+\s+AS\b|CREATE\s+(TABLE|INDEX|VIEW|UNIQUE)|ALTER\s+TABLE|DROP\s+(TABLE|INDEX))",
    re.I | re.S,
)
ENUMS = {
    "Direction",
    "Cadence",
    "AccountKind",
    "AccountType",
    "PlannedStatus",
    "Operation",
    "EntityType",
    "Kind",
}
DOMAIN_ATTRS = {"direction", "kind", "cadence", "status", "account_type"}
FX_NAMES = {
    "convert",
    "convert_cached",
    "to_minor_units",
    "format_money",
    "parse_amount_str",
    "currency_decimals",
    "get_rate",
}
AGG = {"sum", "min", "max", "sorted", "Counter", "groupby", "defaultdict", "reduce", "mean", "fsum"}
ROUTE_DECOS = {"get", "post", "put", "delete", "patch", "head", "options", "api_route", "websocket"}


def is_route(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        c = d.func if isinstance(d, ast.Call) else d
        if isinstance(c, ast.Attribute) and c.attr in ROUTE_DECOS:
            return True
    return False


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
        elif isinstance(x, ast.match_case):
            n += 1
    return n


def has_str(n: ast.AST) -> bool:
    return (isinstance(n, ast.Constant) and isinstance(n.value, str)) or isinstance(
        n, ast.JoinedStr | ast.List | ast.Tuple
    )


def analyse(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, imports: dict[str, str], known: set[str]
) -> set[str]:
    sig: set[str] = set()
    for n in walk(fn):
        if isinstance(n, ast.Call):
            tgt = resolve_call(n, imports, known)
            d = dotted(n.func)
            tail = d.split(".")[-1] if d else ""
            if ".repositories." in tgt + ".":
                sig.add("R")
            if tail in {"execute", "executemany", "executescript"}:
                sig.add("S")
            if tail in {"commit", "rollback", "transaction"}:
                sig.add("T")
            if tail in FX_NAMES:
                sig.add("F")
            if tail in AGG and d in AGG | {
                f"{x}.{tail}" for x in ("statistics", "itertools", "collections", "functools")
            }:
                sig.add("G")
            if (
                tail in {"timedelta", "date", "replace", "monthrange", "relativedelta"}
                and tail != "replace"
            ):
                sig.add("C")
            if tail == "replace" and any(k.arg in {"day", "month", "year"} for k in n.keywords):
                sig.add("C")
        elif isinstance(n, ast.BinOp):
            if isinstance(n.op, ast.Sub | ast.Mult | ast.Div | ast.FloorDiv | ast.Mod | ast.Pow):
                if not (has_str(n.left) or has_str(n.right)) and not (
                    isinstance(n.op, ast.Mod) and isinstance(n.left, ast.Constant)
                ):
                    sig.add("A")
            elif isinstance(n.op, ast.Add) and not (has_str(n.left) or has_str(n.right)):
                sig.add("A")
        elif isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add | ast.Sub | ast.Mult):
            sig.add("G")
        elif isinstance(n, ast.Compare):
            txt = unparse(n, 200)
            if any(re.search(rf"\b{e}\.", txt) for e in ENUMS) or any(
                re.search(rf"\.{a}\b", txt) for a in DOMAIN_ATTRS
            ):
                sig.add("D")
    return sig


def p05() -> None:
    known = module_index()
    rows: list[tuple[str, str, str]] = []
    thin: list[tuple[str, str, str]] = []
    for p in py_files():
        if layer(p) != "web.routers":
            continue
        tree = parse(p)
        mod = module_name(p)
        imports = resolve_imports(tree, mod, False, known)
        for q, fn in func_qualnames(tree):
            if "." in q:  # nested function: counted with its parent
                continue
            lines = (fn.end_lineno or fn.lineno) - fn.lineno + 1
            kind = "route" if is_route(fn) else "helper"
            sig = analyse(fn, imports, known)
            if kind == "helper":
                sig = sig | {"P"}
            tag = f"{kind} L{lines} cc{cc(fn)} | {''.join(sorted(sig)) or '-'}"
            if sig - {"P"}:
                rows.append((f"{rel(p)}:{fn.lineno}", "logic-in-router", f"{q}: {tag}"))
            elif sig == {"P"}:
                rows.append((f"{rel(p)}:{fn.lineno}", "helper-in-router", f"{q}: {tag}"))
            else:
                thin.append((f"{rel(p)}:{fn.lineno}", "thin", f"{q}: {tag}"))
    write(
        "p05-thin-web",
        "P5 thin web. Script: repro/inventory/p05_p06_web_repo.py. Rows: router functions with a business-logic signal\n"
        "(logic-in-router) or a private helper that is not a route and has no other signal (helper-in-router).\n"
        "Signals: R repo call, S SQL, A arithmetic, G aggregation, D domain branch, T txn control, F fx/money call, C date arithmetic, P non-route helper.",
        rows,
    )
    write(
        "p05-thin-web-thin-ok",
        "P5 router functions with NO logic signal (thin, compliant) - for the denominator",
        thin,
    )


def table_flags() -> tuple[set[str], set[str]]:
    soft: set[str] = set()
    user: set[str] = set()
    for p in sorted((ROOT / "migrations").glob("*.sql")):
        txt = p.read_text()
        for m in re.finditer(
            r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)\s*\((.*?)\n\);", txt, re.S | re.I
        ):
            name = re.sub(r"_new$", "", m.group(1))
            if "deleted_at" in m.group(2):
                soft.add(name)
            if re.search(r"\buser_id\b", m.group(2)):
                user.add(name)
    user.add(
        "audit_log"
    )  # user_id added by migrations 0012/0016 (ALTER, not visible in CREATE TABLE)
    return soft, user


def sql_texts(fn: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for n in walk(fn):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and SQL_RE.match(n.value):
            out.append((n.lineno, n.value))
        elif isinstance(n, ast.JoinedStr):
            s = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
            if SQL_RE.match(s):
                out.append((n.lineno, s))
    return out


def p06() -> None:
    soft, user = table_flags()
    outside: list[tuple[str, str, str]] = []
    unaudited: list[tuple[str, str, str]] = []
    reads: list[tuple[str, str, str]] = []
    audit_ok_tables = {
        "sessions",
        "auth_rate_limit",
        "user_preferences",
        "audit_log",
        "schema_meta",
    }
    for p in py_files():
        lay = layer(p)
        tree = parse(p)
        f = rel(p)
        enc = enclosing_function_map(tree)
        if lay != "repositories":
            for n in walk(tree):
                tag = "bootstrap" if lay == "db" or p.name in {"health.py", "app.py"} else "real"
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in {"execute", "executemany", "executescript"}
                ):
                    outside.append(
                        (
                            f"{f}:{n.lineno}",
                            f"sql-exec:{tag}",
                            f"[{lay}] {enc.get(id(n), '<module>')}: {unparse(n, 70)}",
                        )
                    )
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in {"commit", "rollback"}
                    and "conn" in dotted(n.func.value)
                ):
                    outside.append(
                        (
                            f"{f}:{n.lineno}",
                            f"txn-control:{tag}",
                            f"[{lay}] {enc.get(id(n), '<module>')}: {unparse(n, 70)}",
                        )
                    )
                if (
                    isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and SQL_RE.match(n.value)
                    and "\n" in n.value + " "
                ):
                    pass
            for ln, s in sql_texts(tree):
                tag = "bootstrap" if lay == "db" else "real"
                if layer(p) == "domain":
                    tag = "enum-false-positive"
                outside.append(
                    (f"{f}:{ln}", f"sql-literal:{tag}", f"[{lay}] {' '.join(s.split())[:70]}")
                )
            continue
        # repositories: mutation audit + read filters, per top-level function
        for q, fn in func_qualnames(tree):
            if "." in q:
                continue
            calls = {dotted(c.func).split(".")[-1] for c in walk(fn) if isinstance(c, ast.Call)}
            audited = bool(calls & {"mutate", "write_audit"})
            sqls = sql_texts(fn)
            text = " ".join(
                [s for _, s in sqls]
                + [
                    c.value
                    for c in walk(fn)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)
                ]
            )
            for ln, s in sqls:
                m = re.match(r"\s*(INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM)\s+(\w+)", s, re.I)
                if m and not audited:
                    tbl = m.group(2)
                    kind = "exempt-table" if tbl in audit_ok_tables else "unaudited"
                    unaudited.append(
                        (f"{f}:{ln}", f"mutation-{kind}", f"{q}: {m.group(1).split()[0]} {tbl}")
                    )
            # reads
            for ln, s in sqls:
                if not re.match(r"\s*(SELECT|WITH)", s, re.I):
                    continue
                tables = set(re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", s, re.I))
                for t in sorted(tables):
                    intentional = any(
                        a.arg in {"include_deleted", "only_deleted"}
                        for a in fn.args.args + fn.args.kwonlyargs
                    )
                    if t in soft and "deleted_at" not in text:
                        reads.append(
                            (
                                f"{f}:{ln}",
                                "read-no-softdelete" + ("-flag" if intentional else ""),
                                f"{q}: {t}",
                            )
                        )
                    if t in user and "user_id" not in text:
                        reads.append((f"{f}:{ln}", "read-no-user-filter", f"{q}: {t}"))
    write(
        "p06-sql-outside-repos",
        "P6 SQL / txn control outside repositories/. :real = DML/SELECT that belongs in a repository; :bootstrap = PRAGMA/VACUUM/health\n"
        "(db/ package and health/app startup); :enum-false-positive = text match in domain/enums.py.",
        outside,
    )
    write(
        "p06-unaudited-mutations",
        "P6 INSERT/UPDATE/DELETE in repositories/ whose top-level function neither calls mutate() nor write_audit().\n"
        "mutation-unaudited = soft-delete/audit domain table; mutation-exempt-table = ADR-sanctioned unaudited table.\n"
        "Tables with deleted_at: " + ", ".join(sorted(table_flags()[0])),
        unaudited,
    )
    write(
        "p06-read-filters",
        "P6 SELECT in repositories/ touching a soft-delete table without 'deleted_at' (or a user-owned table without 'user_id')\n"
        "anywhere in the same top-level function's SQL. '-flag' suffix = function has include_deleted/only_deleted parameter\n"
        "(intentional). Heuristic: function-level, not statement-level.\n"
        "Soft-delete tables: "
        + ", ".join(sorted(soft))
        + "\nUser-owned tables: "
        + ", ".join(sorted(user)),
        reads,
    )
