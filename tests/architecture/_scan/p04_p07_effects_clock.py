# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912, PLR0915, ERA001, PLC0415
"""P4 side effects in pure layers + P7 clock.

Pure layers (definition used by the inventory):
  domain/            fully pure: no I/O, DB, network, clock, logging, env, random, settings.
  services/          no network / clock / env / random / logging / filesystem / settings singleton;
                     DB access allowed through the passed connection; clock only via an injected port.
  web view-models    web/*.py except app/deps/errors/retention_task/fx_refresh_task/auth_cookies (charts, today_data,
                     htmx, ledger_types, rendering, templating): no network, clock, env.
  repositories/      I/O by definition (DB); clock/env/settings still listed (clock rule P7).
Rules: eff-import (forbidden import), eff-clock, eff-random, eff-env, eff-log, eff-fs, eff-net, eff-print,
eff-settings (hidden settings singleton), eff-subprocess, eff-sleep, eff-net-reach (transitive: calls a
function that performs network I/O), plus P7 rule ``clock`` for every clock call in all of src.
"""

from __future__ import annotations

import ast
import re

from tests.architecture._scan._common import (
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

CLOCK = {
    "date.today",
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "datetime.date.today",
    "time.time",
    "time.monotonic",
    "time.perf_counter",
    "time.time_ns",
    "time.process_time",
    "time.monotonic_ns",
    "time.perf_counter_ns",
}
FORBIDDEN_IMPORTS = {
    "domain": {
        "sqlite3",
        "httpx",
        "requests",
        "urllib.request",
        "socket",
        "os",
        "subprocess",
        "logging",
        "random",
        "secrets",
        "bcrypt",
        "time",
        "uuid",
        "pathlib",
        "shutil",
        "tempfile",
        "asyncio",
        "budget_planner.config",
    },
    "services": {
        "httpx",
        "requests",
        "urllib.request",
        "socket",
        "subprocess",
        "random",
        "secrets",
        "bcrypt",
        "time",
        "logging",
        "shutil",
        "tempfile",
        "budget_planner.config",
    },
    "web-vm": {
        "httpx",
        "requests",
        "urllib.request",
        "socket",
        "subprocess",
        "random",
        "secrets",
        "time",
    },
}
WEB_VM_EXCLUDE = {
    "app",
    "deps",
    "errors",
    "retention_task",
    "fx_refresh_task",
    "auth_cookies",
    "__init__",
}
FS_ATTRS = {
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "unlink",
    "mkdir",
    "rmdir",
    "touch",
    "rename",
}
NET_ROOTS = ("httpx", "requests", "socket", "aiohttp")


def pure_class(p, lay):
    if lay == "domain":
        return "domain"
    if lay == "services":
        return "services"
    if lay == "web" and p.stem not in WEB_VM_EXCLUDE:
        return "web-vm"
    return None


def main() -> None:
    known = module_index()
    files = py_files()
    eff_rows: list[tuple[str, str, str]] = []
    clock_rows: list[tuple[str, str, str]] = []
    # pass 1: direct network functions and call graph (module.function -> callees)
    graph: dict[str, set[str]] = {}
    net_direct: set[str] = set()
    info: dict[str, tuple[str, int]] = {}
    trees = {}
    for p in files:
        tree = parse(p)
        trees[p] = tree
        mod = module_name(p)
        is_pkg = p.name == "__init__.py"
        imports = resolve_imports(tree, mod, is_pkg, known)
        net_aliases = set()
        for n in walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] in NET_ROOTS:
                        net_aliases.add((a.asname or a.name).split(".")[0])
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in NET_ROOTS:
                for a in n.names:
                    net_aliases.add(a.asname or a.name)
        for q, fn in func_qualnames(tree):
            key = f"{mod}.{q}"
            info[key] = (rel(p), fn.lineno)
            callees = graph.setdefault(key, set())
            http_params = {
                a.arg
                for a in [*fn.args.args, *fn.args.kwonlyargs]
                if a.annotation is not None and "httpx" in unparse(a.annotation)
            }
            for n in walk(fn):
                if isinstance(n, ast.Call):
                    d = dotted(n.func)
                    if d and d.split(".")[0] in net_aliases:
                        net_direct.add(key)
                    if d and d.split(".")[0] in http_params:
                        net_direct.add(key)
                    tgt = resolve_call(n, imports, known)
                    if tgt:
                        callees.add(tgt)
                    elif isinstance(n.func, ast.Name):
                        callees.add(f"{mod}.{n.func.id}")
    reach: dict[str, str] = dict.fromkeys(net_direct, "direct")
    changed = True
    while changed:
        changed = False
        for k, cs in graph.items():
            if k in reach:
                continue
            for c in sorted(cs):
                if c in reach:
                    reach[k] = c
                    changed = True
                    break

    for p in files:
        tree = parse(p)
        f = rel(p)
        lay = layer(p)
        pc = pure_class(p, lay)
        mod = module_name(p)
        enc = enclosing_function_map(tree)
        # imports
        if pc:
            for n in walk(tree):
                names = []
                if isinstance(n, ast.Import):
                    names = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                    names = [n.module]
                for nm in names:
                    for bad in FORBIDDEN_IMPORTS[pc]:
                        if nm == bad or nm.startswith(bad + "."):
                            eff_rows.append(
                                (f"{f}:{n.lineno}", "eff-import", f"[{pc}] imports {nm}")
                            )
        for n in walk(tree):
            if isinstance(n, ast.Call):
                d = dotted(n.func)
                fn_name = enc.get(id(n), "<module>")
                tail = d.split(".")[-1] if d else ""
                # P7 clock (all layers)
                if d in CLOCK or (tail in {"now", "utcnow", "today"} and "." in d):
                    tz = "tz-arg" if (n.args or n.keywords) else "no-arg"
                    clock_rows.append(
                        (f"{f}:{n.lineno}", "clock", f"[{lay}] {fn_name}: {unparse(n, 60)} ({tz})")
                    )
                if not pc:
                    continue
                tag = f"[{pc}] {fn_name}: {unparse(n, 60)}"
                where = f"{f}:{n.lineno}"
                if d in CLOCK or (tail in {"now", "utcnow", "today"} and "." in d):
                    eff_rows.append((where, "eff-clock", tag))
                elif d in {"time.sleep", "asyncio.sleep"}:
                    eff_rows.append((where, "eff-sleep", tag))
                elif d.split(".")[0] in {"random", "secrets"} or tail in {
                    "uuid4",
                    "uuid1",
                    "token_hex",
                    "token_urlsafe",
                    "randbelow",
                }:
                    eff_rows.append((where, "eff-random", tag))
                elif d in {"os.getenv", "os.environ.get", "getenv"}:
                    eff_rows.append((where, "eff-env", tag))
                elif d.split(".")[0] in {
                    "logging",
                    "logger",
                    "log",
                    "_logger",
                    "_log",
                } and tail in {
                    "debug",
                    "info",
                    "warning",
                    "error",
                    "exception",
                    "critical",
                    "getLogger",
                    "basicConfig",
                    "warn",
                    "log",
                }:
                    eff_rows.append((where, "eff-log", tag))
                elif d in {"open", "Path.open"} or tail in FS_ATTRS:
                    eff_rows.append((where, "eff-fs", tag))
                elif d == "print":
                    eff_rows.append((where, "eff-print", tag))
                elif d == "get_settings" or d.endswith(".get_settings"):
                    eff_rows.append((where, "eff-settings", tag))
                elif d.split(".")[0] == "subprocess":
                    eff_rows.append((where, "eff-subprocess", tag))
                elif d.split(".")[0] in NET_ROOTS:
                    eff_rows.append((where, "eff-net", tag))
            if pc and isinstance(n, ast.Attribute) and dotted(n) in {"os.environ", "sys.argv"}:
                eff_rows.append((f"{f}:{n.lineno}", "eff-env", f"[{pc}] {dotted(n)}"))
        if pc:
            for q, fn in func_qualnames(tree):
                key = f"{mod}.{q}"
                r = reach.get(key)
                if r and r != "direct":
                    eff_rows.append((f"{f}:{fn.lineno}", "eff-net-reach", f"[{pc}] {q} -> {r}"))
                elif r == "direct":
                    eff_rows.append(
                        (f"{f}:{fn.lineno}", "eff-net", f"[{pc}] {q} performs network I/O directly")
                    )

    # routers / middleware / other layers that reach the network (info for P4 'render path' view)
    for p in files:
        lay = layer(p)
        if lay in {"web.routers", "web.middleware"} or (
            lay == "web" and pure_class(p, lay) is None
        ):
            tree = trees[p]
            mod = module_name(p)
            for q, fn in func_qualnames(tree):
                r = reach.get(f"{mod}.{q}")
                if r and r != "direct":
                    eff_rows.append(
                        (f"{rel(p)}:{fn.lineno}", "eff-net-reach-web", f"[{lay}] {q} -> {r}")
                    )

    write(
        "p04-side-effects",
        "P4 side effects in pure layers. Script: repro/inventory/p04_p07_effects_clock.py\n"
        "Pure layers: domain (strict), services (no net/clock/env/random/log/fs/settings), web view-models.\n"
        "eff-net-reach = function transitively calls a function that performs network I/O (name-resolved call graph,\n"
        "approximate: first reachable callee shown).",
        eff_rows,
    )
    write(
        "p07-clock",
        "P7 clock (ADR-0007). Script: repro/inventory/p04_p07_effects_clock.py\n"
        "Every date.today / datetime.now / utcnow / time.time / monotonic / perf_counter call in src (all layers).\n"
        "tz-arg = call passes a tz or other arg (aware); no-arg = naive host-clock.",
        clock_rows,
    )
    # SQL-level clock
    sql_clock: list[tuple[str, str, str]] = []
    pat = re.compile(
        r"CURRENT_TIMESTAMP|CURRENT_DATE|datetime\(\s*'now'|date\(\s*'now'|strftime\([^)]*'now'",
        re.I,
    )
    for p in files:
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if pat.search(line):
                sql_clock.append((f"{rel(p)}:{i}", "sql-clock", line.strip()[:100]))
    write("p07-clock-sql", "P7 DB-side clock in SQL strings (src)", sql_clock)
    # SQL files
    from tests.architecture._scan._common import ROOT

    mig = []
    for p in sorted((ROOT / "migrations").glob("*.sql")):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if pat.search(line):
                mig.append(
                    (f"{p.relative_to(ROOT).as_posix()}:{i}", "sql-clock", line.strip()[:100])
                )
    write(
        "p07-clock-migrations",
        "P7 DB-side clock in migrations (informational: DEFAULT CURRENT_TIMESTAMP is schema, not code)",
        mig,
    )
