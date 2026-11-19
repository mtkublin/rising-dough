"""Track F: redundant-test candidates from per-test coverage contexts (ADR-0108 s2).

Usage: python redundant_candidates.py <coverage-data-file>
The data file comes from `pytest --cov-context=test` (see README in track F).
A test is a candidate when every line it covers is also covered by at least one
other test (zero unique lines).  Candidates are CHECKED BY HAND before they
become findings; this script only ranks them.
"""

import collections
import sys

from coverage import CoverageData

data = CoverageData(sys.argv[1])
data.read()
line_ctx: dict[tuple[str, int], set[str]] = collections.defaultdict(set)
test_lines: dict[str, set[tuple[str, int]]] = collections.defaultdict(set)
for f in data.measured_files():
    for line, ctxs in (data.contexts_by_lineno(f) or {}).items():
        for c in ctxs:
            if not c:
                continue
            c = c.split("|")[0]
            line_ctx[(f, line)].add(c)
            test_lines[c].add((f, line))

unique = {t: 0 for t in test_lines}
for key, ctxs in line_ctx.items():
    if len(ctxs) == 1:
        unique[next(iter(ctxs))] += 1

print("tests with contexts:", len(test_lines))
zero = sorted(t for t, n in unique.items() if n == 0)
print("zero-unique-line tests:", len(zero))
by_file = collections.Counter(t.split("::")[0] for t in zero)
tot_by_file = collections.Counter(t.split("::")[0] for t in test_lines)
print("\nper file (zero-unique / total):")
for f, n in by_file.most_common(40):
    print(f"  {f}: {n}/{tot_by_file[f]}")

# identical coverage sets within the same module
groups: dict[tuple[str, frozenset], list[str]] = collections.defaultdict(list)
for t, ls in test_lines.items():
    groups[(t.split("::")[0], frozenset(ls))].append(t)
dups = [v for v in groups.values() if len(v) > 1]
print("\nsame-module identical-coverage groups:", len(dups))
for v in sorted(dups, key=len, reverse=True)[:40]:
    print("  ", len(v), v[:4])
print("\nZERO-UNIQUE LIST")
for t in zero:
    print(t, len(test_lines[t]))
