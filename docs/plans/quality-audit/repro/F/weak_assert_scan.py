"""Track F: AST scan of tests/ for weak-assertion test functions (read-only).

Run from the repo root:  python3 docs/plans/quality-audit/repro/F/weak_assert_scan.py
"""

import ast
import collections
import pathlib


def is_status(n: ast.AST) -> bool:
    return isinstance(n, ast.Compare) and "status_code" in ast.unparse(n.left)


def is_not_none(n: ast.AST) -> bool:
    return (
        isinstance(n, ast.Compare)
        and len(n.ops) == 1
        and isinstance(n.ops[0], ast.IsNot)
        and isinstance(n.comparators[0], ast.Constant)
        and n.comparators[0].value is None
    )


def kinds(fn: ast.AST) -> list[str]:
    out: list[str] = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert):
            t = n.test
            if is_status(t):
                out.append("status")
            elif is_not_none(t):
                out.append("notnone")
            elif isinstance(t, (ast.Name, ast.Attribute)):
                out.append("truthy")
            else:
                out.append("other")
        elif isinstance(n, ast.With):
            for it in n.items:
                src = ast.unparse(it.context_expr)
                if "raises" in src or "warns" in src:
                    out.append("raises")
        elif isinstance(n, ast.Call):
            nm = ast.unparse(n.func)
            if nm.startswith(("assert_", "expect", "pytest.fail")) or ".assert_" in nm:
                out.append("other")
    return out


def main() -> None:
    res: dict[str, list[tuple[str, int, str]]] = collections.defaultdict(list)
    total = 0
    for p in sorted(pathlib.Path("tests").rglob("test_*.py")):
        tree = ast.parse(p.read_text())
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name.startswith(
                "test_"
            ):
                k = kinds(fn)
                total += 1
                ent = (str(p), fn.lineno, fn.name)
                if not k:
                    res["noassert"].append(ent)
                elif set(k) == {"status"}:
                    res["status_only"].append(ent)
                elif set(k) <= {"status", "notnone"}:
                    res["status_or_notnone_only"].append(ent)
                elif set(k) == {"notnone"}:
                    res["notnone_only"].append(ent)
                elif set(k) == {"truthy"}:
                    res["truthy_only"].append(ent)
    print("total test functions", total)
    for key, v in res.items():
        print("==", key, len(v))
        for x in v:
            print("  %s:%d %s" % x)


main()
