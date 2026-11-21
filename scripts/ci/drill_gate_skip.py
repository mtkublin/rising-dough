"""Classify a PR's changed paths as `skip` or `gate` for the drill-gate (ADR-0121).

Reads one path per line on stdin (for a rename, both the old and the new path).
Prints `skip` when EVERY path is on the allowlist (`docs/` only, ADR-0121 amendment
2026-11-21), else `gate` followed by the deploy-relevant paths, one per line. An empty
input is `gate` (fail closed).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence

# T-Q238 (Q-042, ADR-0121 amendment 2026-11-21): the skip allowlist is `docs/`
# ONLY. `.claude/` (agent hooks and instructions), `tests/` (run in the release
# ci job and by terraform.yml), top-level markdown and LICENSE files are all
# gated: each can change what the pipeline or an agent does.
SAFE_DIR = "docs"

# Files under docs/ that a workflow or script reads at run time, so a change
# is deploy-relevant. test_drill_gate_skip.py greps .github/ and scripts/ci/
# and fails when one references a docs/ path missing from this list.
DOCS_CONSUMED_BY_PIPELINE: tuple[str, ...] = ("docs/plans/v3/runbooks/restore-log.md",)


def _is_safe(path: str) -> bool:
    if path.startswith("/") or ".." in path.split("/") or "\\" in path:
        return False
    if path in DOCS_CONSUMED_BY_PIPELINE:
        return False
    top, _, rest = path.partition("/")
    return bool(rest) and top == SAFE_DIR


def classify(paths: Iterable[str]) -> tuple[str, list[str]]:
    """Return (`skip`|`gate`, deploy-relevant paths). Empty input is `gate`."""
    cleaned = [p.strip() for p in paths if p.strip()]
    if not cleaned:
        return "gate", []
    offenders = [p for p in cleaned if not _is_safe(p)]
    return ("gate", offenders) if offenders else ("skip", [])


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    verdict, offenders = classify(sys.stdin.read().splitlines())
    print("\n".join([verdict, *offenders]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
