"""Track F: services functions that no tests/unit test executes (mutmut "no tests" proxy).

Usage: python functions_without_unit_tests.py <coverage-data-file> <repo-root>
Needs a coverage file recorded with `--cov-context=test`.
"""

import ast
import collections
import sys

from coverage import CoverageData

data = CoverageData(sys.argv[1])
data.read()
root = sys.argv[2].rstrip("/") + "/"
for mod in ["budget", "balance", "forecast", "rate_limit", "auth", "reauth"]:
    path = root + f"src/budget_planner/services/{mod}.py"
    tree = ast.parse(open(path).read())
    lc = data.contexts_by_lineno(path)
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        ctxs: set[str] = set()
        for line in range(fn.lineno, fn.end_lineno + 1):
            ctxs |= {c.split("|")[0] for c in lc.get(line, []) if c}
        if any(c.startswith("tests/unit/") for c in ctxs):
            continue
        kinds = collections.Counter(c.split("/")[1] for c in ctxs)
        print(mod, fn.name, fn.lineno, dict(kinds))
