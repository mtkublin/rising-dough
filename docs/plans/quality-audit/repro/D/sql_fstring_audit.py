"""List every interpolation inside SQL-looking f-strings / concatenations under src/ (T-Q07 SQLi review).

Run: uv run python docs/plans/quality-audit/repro/D/sql_fstring_audit.py > sql_fstring_audit_output.txt
Read-only static scan; prints `file:line  {expr}` per interpolation so a human can classify each as
constant-fragment (safe) or request-derived (injectable).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", re.I)
for path in sorted(Path("src/budget_planner").rglob("*.py")):
    src = path.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            lit = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if SQL.search(lit):
                exprs = [ast.get_source_segment(src, v.value) for v in node.values if isinstance(v, ast.FormattedValue)]
                print(f"{path}:{node.lineno}  {exprs}")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            seg = ast.get_source_segment(src, node) or ""
            if SQL.search(seg) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str) and SQL.search(node.left.value):
                print(f"{path}:{node.lineno}  CONCAT/%: {seg[:100]!r}")
