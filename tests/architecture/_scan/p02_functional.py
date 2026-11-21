# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912
"""P2 functional-first (ADR-0021): classes, non-frozen dataclasses, module-level state,
``global``, mutable defaults, ``lru_cache``/hidden caches.

Rules emitted
  class-plain          class that is not a frozen dataclass/NamedTuple/TypedDict/Protocol/Enum/Exception/pydantic DTO
  class-framework      subclass of a framework base (ASGI middleware) - letter violation, framework-imposed
  dataclass-not-frozen @dataclass without frozen=True
  class-nested         class defined inside a function
  mutable-constant     module-level list/dict/set literal or constructor (should be tuple/frozenset/MappingProxyType)
  module-state         module-level lock / ContextVar / client
  module-singleton     module-level instance built by a project or framework call (settings, router, templates, app)
  global-stmt          ``global`` statement
  mutable-default      mutable default argument
  hidden-cache         functools.cache / lru_cache / cached_property (process-wide hidden state)
Accepted (not listed): frozen dataclass, NamedTuple, TypedDict, Protocol, Enum family, Exception subclasses,
pydantic BaseModel / BaseSettings (DTO).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from tests.architecture._scan._common import (
    dotted,
    layer,
    parse,
    py_files,
    rel,
    unparse,
    walk,
    write,
)

OK_BASES = {
    "NamedTuple",
    "TypedDict",
    "Protocol",
    "Enum",
    "StrEnum",
    "IntEnum",
    "Flag",
    "IntFlag",
    "BaseModel",
    "BaseSettings",
    "Generic",
}
FRAMEWORK_BASES = {"BaseHTTPMiddleware"}
MUT_CTORS = {"list", "dict", "set", "defaultdict", "OrderedDict", "deque", "Counter", "bytearray"}
STATE_CTORS = {
    "Lock",
    "RLock",
    "Semaphore",
    "Event",
    "ContextVar",
    "local",
    "Queue",
    "Client",
    "AsyncClient",
}
PURE_CALLS = {
    "frozenset",
    "tuple",
    "compile",
    "ZoneInfo",
    "Decimal",
    "TypeVar",
    "NewType",
    "namedtuple",
    "Path",
    "getLogger",
    "MappingProxyType",
    "field",
    "Final",
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "object",
    "TypeAliasType",
    "timedelta",
    "date",
    "datetime",
    "Annotated",
    "Literal",
    "cast",
    "PurePosixPath",
    "ParamSpec",
    "TypeAlias",
}


def base_names(c: ast.ClassDef) -> list[str]:
    return [dotted(b).split(".")[-1] if dotted(b) else unparse(b, 30) for b in c.bases]


def dc_info(c: ast.ClassDef) -> tuple[bool, bool]:
    """(is_dataclass, frozen)."""
    for d in c.decorator_list:
        name = dotted(d.func if isinstance(d, ast.Call) else d)
        if name.split(".")[-1] == "dataclass":
            if isinstance(d, ast.Call):
                for kw in d.keywords:
                    if kw.arg == "frozen":
                        return True, bool(
                            isinstance(kw.value, ast.Constant) and kw.value.value is True
                        )
            return True, False
    return False, False


def is_exception(bases: list[str]) -> bool:
    return any(b.endswith(("Error", "Exception", "Warning")) for b in bases)


def module_stmts(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    for s in body:
        yield s
        if isinstance(s, ast.If):
            yield from module_stmts(s.body)
            yield from module_stmts(s.orelse)
        elif isinstance(s, ast.Try):
            yield from module_stmts(s.body)
            for h in s.handlers:
                yield from module_stmts(h.body)
            yield from module_stmts(s.orelse)


def main() -> None:
    rows: list[tuple[str, str, str]] = []
    for p in py_files():
        tree = parse(p)
        f = rel(p)
        lay = layer(p)

        fn_nodes = [n for n in walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
        inner = {id(c) for fn in fn_nodes for c in walk(fn) if isinstance(c, ast.ClassDef)}
        for c in [n for n in walk(tree) if isinstance(n, ast.ClassDef)]:
            bases = base_names(c)
            is_dc, frozen = dc_info(c)
            where = f"{f}:{c.lineno}"
            if id(c) in inner:
                rows.append((where, "class-nested", f"{c.name}({', '.join(bases)}) [{lay}]"))
            if is_dc:
                if not frozen:
                    rows.append((where, "dataclass-not-frozen", f"{c.name} [{lay}]"))
                continue
            if any(b in OK_BASES for b in bases) or is_exception(bases):
                continue
            kind = "class-framework" if any(b in FRAMEWORK_BASES for b in bases) else "class-plain"
            rows.append((where, kind, f"{c.name}({', '.join(bases)}) [{lay}]"))

        for s in module_stmts(tree.body):
            if not isinstance(s, ast.Assign | ast.AnnAssign) or s.value is None:
                continue
            val = s.value
            targets = s.targets if isinstance(s, ast.Assign) else [s.target]
            tname = ", ".join(unparse(t, 30) for t in targets)
            if tname in {"__all__", "__slots__"}:
                continue
            where = f"{f}:{s.lineno}"
            if isinstance(
                val, ast.List | ast.Dict | ast.Set | ast.ListComp | ast.DictComp | ast.SetComp
            ):
                rows.append((where, "mutable-constant", f"{tname} = {unparse(val, 50)}"))
            elif isinstance(val, ast.Call):
                cn = dotted(val.func).split(".")[-1]
                if cn in MUT_CTORS:
                    rows.append((where, "mutable-constant", f"{tname} = {unparse(val, 50)}"))
                elif cn in STATE_CTORS:
                    rows.append((where, "module-state", f"{tname} = {unparse(val, 50)}"))
                elif cn not in PURE_CALLS:
                    rows.append((where, "module-singleton", f"{tname} = {unparse(val, 60)}"))

        for n in walk(tree):
            if isinstance(n, ast.Global):
                rows.append((f"{f}:{n.lineno}", "global-stmt", f"global {', '.join(n.names)}"))
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                defaults = [*n.args.defaults, *[k for k in n.args.kw_defaults if k is not None]]
                for d in defaults:
                    if isinstance(d, ast.List | ast.Dict | ast.Set) or (
                        isinstance(d, ast.Call) and dotted(d.func).split(".")[-1] in MUT_CTORS
                    ):
                        rows.append(
                            (
                                f"{f}:{d.lineno}",
                                "mutable-default",
                                f"{n.name}(... = {unparse(d, 40)})",
                            )
                        )
                for d in n.decorator_list:
                    dn = dotted(d.func if isinstance(d, ast.Call) else d).split(".")[-1]
                    if dn in {"cache", "lru_cache", "cached_property"}:
                        rows.append((f"{f}:{n.lineno}", "hidden-cache", f"@{dn} {n.name}"))
    write(
        "p02-functional",
        "P2 functional-first (ADR-0021). Script: repro/inventory/p02_functional.py\n"
        "Rules: class-plain, class-framework, dataclass-not-frozen, class-nested, mutable-constant, module-state,\n"
        "module-singleton, global-stmt, mutable-default, hidden-cache.",
        rows,
    )
