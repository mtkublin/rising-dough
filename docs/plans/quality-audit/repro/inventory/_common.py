"""Shared helpers for the T-Q14b compliance-inventory scanners.

Every scanner is stdlib-only (``ast``/``re``/``tomllib``), read-only, and writes a
tab-separated, sorted file ``docs/plans/quality-audit/inventory/<name>.txt``:

    <path>:<line>\t<rule>\t<detail>

Run all with ``bash docs/plans/quality-audit/repro/inventory/run_all.sh`` from the
repository root. Output is deterministic (sorted); re-running on an unchanged tree
produces no diff. Nothing opens ``data/budget.sqlite`` and nothing is imported from
``src`` (files are parsed, never executed).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "src" / "budget_planner"
TEMPLATES = SRC / "web" / "templates"
STATIC = SRC / "web" / "static"
OUT = ROOT / "docs" / "plans" / "quality-audit" / "inventory"
PKG = "budget_planner"


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def py_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def module_name(p: Path) -> str:
    parts = list(p.relative_to(SRC.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def layer(p: Path) -> str:
    """Architectural layer of a source file."""
    parts = p.relative_to(SRC).parts
    if len(parts) == 1:
        return "root"
    top = parts[0]
    if top == "web":
        if len(parts) > 1 and parts[1] == "routers":
            return "web.routers"
        if len(parts) > 1 and parts[1] == "middleware":
            return "web.middleware"
        return "web"
    return top


def parse(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def src_lines(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


def functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
            yield n


def func_qualnames(tree: ast.Module) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Yield (qualified name, node) for every function, including nested and methods."""

    def walk(node: ast.AST, prefix: str) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef):
                q = f"{prefix}{ch.name}"
                yield q, ch
                yield from walk(ch, q + ".")
            elif isinstance(ch, ast.ClassDef):
                yield from walk(ch, f"{prefix}{ch.name}.")
            else:
                yield from walk(ch, prefix)

    yield from walk(tree, "")


def enclosing_function_map(tree: ast.Module) -> dict[int, str]:
    """Map id(node) -> qualified name of the innermost enclosing function ('<module>' if none)."""
    result: dict[int, str] = {}

    def visit(node: ast.AST, cur: str, prefix: str) -> None:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef):
                q = f"{prefix}{ch.name}"
                result[id(ch)] = cur
                visit(ch, q, q + ".")
            elif isinstance(ch, ast.ClassDef):
                result[id(ch)] = cur
                visit(ch, cur, f"{prefix}{ch.name}.")
            else:
                result[id(ch)] = cur
                visit(ch, cur, prefix)

    visit(tree, "<module>", "")
    return result


def dotted(node: ast.AST) -> str:
    """Dotted name of a Name/Attribute chain ('' when not a plain chain)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


def root_name(node: ast.AST) -> str:
    """Leftmost Name of an Attribute/Subscript/Call chain ('' if none)."""
    while isinstance(node, ast.Attribute | ast.Subscript | ast.Call):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ""


def unparse(node: ast.AST, limit: int = 90) -> str:
    try:
        s = ast.unparse(node)
    except Exception:  # noqa: BLE001 - tooling only
        s = "<unparse failed>"
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def write(name: str, header: str, rows: Iterable[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Write ``inventory/<name>.txt`` (sorted, tab-separated) and return the rows."""
    OUT.mkdir(parents=True, exist_ok=True)

    def key(r: tuple[str, str, str]) -> tuple[str, int, str, str]:
        m = re.match(r"^(.*?):(\d+)$", r[0])
        return (m.group(1), int(m.group(2)), r[1], r[2]) if m else (r[0], 0, r[1], r[2])

    data = sorted(set(rows), key=key)
    lines = [f"# {h}" for h in header.strip().splitlines()]
    lines.append(f"# rows: {len(data)}")
    lines.extend("\t".join(r).rstrip() for r in data)
    (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return data


# --- import resolution ---------------------------------------------------------


def module_index() -> set[str]:
    return {module_name(p) for p in py_files()}


def resolve_imports(tree: ast.Module, mod: str, is_pkg: bool, known: set[str]) -> dict[str, str]:
    """Local name -> dotted target ('pkg.mod' or 'pkg.mod.symbol') for first-party imports."""
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith(PKG):
                    out[a.asname or a.name.split(".")[0]] = a.name if a.asname else PKG
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                pkg = mod.split(".") if is_pkg else mod.split(".")[:-1]
                pkg = pkg[: len(pkg) - (n.level - 1)]
                base = ".".join(pkg + ([n.module] if n.module else []))
            if not base.startswith(PKG):
                continue
            for a in n.names:
                full = f"{base}.{a.name}"
                out[a.asname or a.name] = full
    return out


def def_index(files: list[Path]) -> dict[str, set[str]]:
    """module -> set of top-level function names (for resolving symbol calls)."""
    idx: dict[str, set[str]] = {}
    for p in files:
        t = parse(p)
        idx[module_name(p)] = {n.name for n in t.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    return idx


def resolve_call(call: ast.Call, imports: dict[str, str], known_mods: set[str]) -> str:
    """Resolve a call to 'module.function' when it targets first-party code, else ''."""
    f = call.func
    if isinstance(f, ast.Name):
        tgt = imports.get(f.id)
        return tgt or ""
    if isinstance(f, ast.Attribute):
        base = dotted(f.value)
        if not base:
            return ""
        head = base.split(".")[0]
        tgt = imports.get(head)
        if not tgt:
            return ""
        rest = base.split(".")[1:]
        full = ".".join([tgt, *rest])
        return f"{full}.{f.attr}"
    return ""
