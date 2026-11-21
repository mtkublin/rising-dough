#!/usr/bin/env python3
"""Mutation report: scores per package and post-filtered survivors (ADR-0131).

Reads ``mutmut results --all true`` (run ``just mutate`` first), prints the score
per package, and lists survivors by module after dropping:

- equivalent mutants matched by a known diff pattern (``mutmut-equivalent.md``);
  new equivalents are marked ``# pragma: no mutate -- equivalent: <reason>`` on
  the source line instead, and mutmut then never generates them;
- low-value message/log string mutants (``mutmut-exclusions.md``): logger and
  ``raise`` messages, ``XX...XX`` string mutations. Contract strings (status,
  kind, action, entity type, error ``code=``) stay mutated.

``--check`` compares the scores with the committed baseline and exits 1 when a
package drops by more than ``--max-drop`` points (used by ``mutation.yml``).
``--no-diff`` skips the per-survivor ``mutmut show`` calls (scores only).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PACKAGES = ("domain", "services")
BASELINE_PATH = Path(__file__).with_name("mutation_baseline.json")
DEFAULT_MAX_DROP = 2.0
RESULT_LINE = re.compile(r"^\s*(?P<name>\S+__mutmut_\d+):\s*(?P<status>.+?)\s*$")
CONTRACT_KEYS = re.compile(r"""\b(code|status|kind|action|entity_type)\s*=""")
LOG_OR_RAISE = re.compile(
    r"logger\.(debug|info|warning|error|exception)\(|get_logger\(|\braise \w+\("
)
STRING_NOISE = re.compile(r"""["']XX[^"']*XX["']""")
EQUIVALENT_PATTERNS: Sequence[tuple[str, re.Pattern[str]]] = (
    ("quantize rounding=None is ROUND_HALF_EVEN", re.compile(r"rounding=None")),
    ("codec alias UTF-8 == utf-8", re.compile(r'encode\("UTF-8"\)')),
    ("sqlite3.Row lookup is case-insensitive", re.compile(r"""row\[["'][A-Z_]+["']\]""")),
)


@dataclass(frozen=True)
class Mutant:
    name: str
    status: str

    @property
    def module(self) -> str:
        return self.name.split(".x_")[0].split(".xǁ")[0]


def parse_results(text: str) -> list[Mutant]:
    """Parse ``mutmut results --all true`` output into mutants."""
    return [
        Mutant(m["name"], m["status"])
        for line in text.splitlines()
        if (m := RESULT_LINE.match(line))
    ]


def package_of(mutant: Mutant) -> str:
    """Return ``domain`` or ``services`` for a mutant name (``budget_planner.<pkg>...``)."""
    parts = mutant.name.split(".")
    if parts[0] == "budget_planner" and len(parts) > 1:
        return parts[1]
    return parts[0]


def scores(mutants: Iterable[Mutant]) -> dict[str, dict[str, float]]:
    """Per-package counts and killed % of testable (killed + survived + timeout)."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for m in mutants:
        counts[package_of(m)][m.status] += 1
    out: dict[str, dict[str, float]] = {}
    for pkg, c in sorted(counts.items()):
        killed, survived, timeout = c["killed"], c["survived"], c["timeout"]
        testable = killed + survived + timeout
        out[pkg] = {
            "mutants": float(sum(c.values())),
            "killed": float(killed),
            "survived": float(survived),
            "timeout": float(timeout),
            "no_tests": float(c["no tests"]),
            "killed_pct_testable": round(100.0 * killed / testable, 1) if testable else 0.0,
        }
    return out


def classify(diff: str) -> str:
    """Return ``equivalent``, ``low-value`` or ``real`` for a survivor diff."""
    changed = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    added = " ".join(
        line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    for _reason, pattern in EQUIVALENT_PATTERNS:
        if pattern.search(added):
            return "equivalent"
    body = " ".join(changed)
    if CONTRACT_KEYS.search(body):
        return "real"
    if LOG_OR_RAISE.search(body) or (STRING_NOISE.search(added) and " " in added):
        return "low-value"
    return "real"


def check_drop(
    current: Mapping[str, Mapping[str, float]],
    baseline: Mapping[str, float],
    max_drop: float,
) -> list[str]:
    """Return failure messages for packages that fell more than ``max_drop`` points."""
    failures: list[str] = []
    for pkg, base in baseline.items():
        now = current.get(pkg, {}).get("killed_pct_testable")
        if now is None:
            failures.append(f"{pkg}: no result (baseline {base}%)")
        elif now < base - max_drop:
            failures.append(f"{pkg}: {now}% is more than {max_drop} points below baseline {base}%")
    return failures


def _run(cmd: Sequence[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout  # noqa: S603


def _survivor_diffs(names: Iterable[str], show: Callable[[str], str]) -> dict[str, str]:
    return {n: show(n) for n in names}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if a score dropped vs the baseline")
    ap.add_argument("--max-drop", type=float, default=DEFAULT_MAX_DROP)
    ap.add_argument("--no-diff", action="store_true", help="scores only; skip survivor diffs")
    ap.add_argument("--json", type=Path, help="write the scores as JSON to this path")
    args = ap.parse_args(argv)

    mutants = parse_results(_run(["uv", "run", "mutmut", "results", "--all", "true"]))
    if not mutants:
        print("no mutmut results found; run `just mutate` first", file=sys.stderr)
        return 2
    table = scores(mutants)
    print(
        f"{'package':10} {'mutants':>8} {'killed':>7} {'surv':>6} "
        f"{'tmo':>4} {'notest':>7} {'%testable':>10}"
    )
    for pkg, s in table.items():
        print(
            f"{pkg:10} {s['mutants']:8.0f} {s['killed']:7.0f} {s['survived']:6.0f} "
            f"{s['timeout']:4.0f} {s['no_tests']:7.0f} {s['killed_pct_testable']:9.1f}%"
        )
    if args.json:
        args.json.write_text(json.dumps(table, indent=2) + "\n")

    if not args.no_diff:
        survivors = [m for m in mutants if m.status == "survived"]
        diffs = _survivor_diffs(
            (m.name for m in survivors), lambda n: _run(["uv", "run", "mutmut", "show", n])
        )
        by_module: dict[str, list[str]] = defaultdict(list)
        dropped: Counter[str] = Counter()
        for m in survivors:
            kind = classify(diffs[m.name])
            if kind == "real":
                by_module[m.module].append(m.name)
            else:
                dropped[kind] += 1
        print(
            f"\nsurvivors after filter: {sum(map(len, by_module.values()))} "
            f"(dropped {dict(dropped)})"
        )
        for module, names in sorted(by_module.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(names):4}  {module}")

    if args.check:
        baseline = json.loads(BASELINE_PATH.read_text())["killed_pct_testable"]
        failures = check_drop(table, baseline, args.max_drop)
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
