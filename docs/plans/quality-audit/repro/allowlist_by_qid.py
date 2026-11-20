# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""List architecture-guard allowlist entries per finding (Q-id / inventory id) and per remediation epic.

T-Q17 remediation tasks use this as their "removes allowlist entries" field (ADR-0130 section 2).

    python3 docs/plans/quality-audit/repro/allowlist_by_qid.py              # summary: counts per finding, per epic
    python3 docs/plans/quality-audit/repro/allowlist_by_qid.py Q-007        # every entry for one finding
    python3 docs/plans/quality-audit/repro/allowlist_by_qid.py --epic E10   # every entry for one epic
    python3 docs/plans/quality-audit/repro/allowlist_by_qid.py --guard purity

Stdlib only; reads ``tests/architecture/allowlists/*.toml``. ``framework`` and ``permanent`` entries are listed
separately and are not part of the burn-down total.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from pathlib import Path

ALLOWLISTS = Path(__file__).resolve().parents[4] / "tests" / "architecture" / "allowlists"
TABLES = ("entry", "permanent", "framework")


def load() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(ALLOWLISTS.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for table in TABLES:
            for raw in data.get(table, []):
                rows.append({"guard": path.stem, "table": table, **raw})
    return rows


def show(rows: list[dict[str, object]]) -> None:
    for r in rows:
        rule = f" [{r['rule']}]" if r.get("rule") else ""
        print(
            f"{r['guard']:<18} {r['table']:<9} {r['count']:>3}  {r['path']}{rule}  ({r.get('finding', '')} {r.get('epic', '')})"
        )


def summary(rows: list[dict[str, object]]) -> None:
    burn = [r for r in rows if r["table"] == "entry"]
    for label, key in (("finding", "finding"), ("epic", "epic")):
        counts: Counter[str] = Counter()
        for r in burn:
            counts[str(r.get(key) or "-")] += int(r["count"])  # type: ignore[call-overload]
        print(f"== burn-down violations per {label} (total {sum(counts.values())})")
        for name, n in sorted(counts.items()):
            print(f"  {name:<12} {n}")
    for table in ("permanent", "framework"):
        n = sum(int(r["count"]) for r in rows if r["table"] == table)  # type: ignore[call-overload]
        print(f"== {table} (not counted toward zero): {n}")
    guards = Counter(str(r["guard"]) for r in burn)
    print("== burn-down entries per guard")
    for g, n in sorted(guards.items()):
        print(f"  {g:<18} {n}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("finding", nargs="?", help="Q-id or inventory id, e.g. Q-007")
    parser.add_argument("--epic", help="remediation epic, e.g. E10")
    parser.add_argument("--guard", help="guard allowlist stem, e.g. purity")
    args = parser.parse_args()
    rows = load()
    if not (args.finding or args.epic or args.guard):
        summary(rows)
        return 0
    chosen = [
        r
        for r in rows
        if (not args.finding or r.get("finding") == args.finding)
        and (not args.epic or r.get("epic") == args.epic)
        and (not args.guard or r["guard"] == args.guard)
    ]
    show(chosen)
    return 0 if chosen else 1


if __name__ == "__main__":
    sys.exit(main())
