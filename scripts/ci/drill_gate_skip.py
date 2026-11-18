"""Classify a PR's changed paths as `skip` or `gate` for the drill-gate (ADR-0121).

Reads one path per line on stdin (for a rename, both the old and the new path).
Prints `skip` when EVERY path is on the non-deploy allowlist, else `gate` followed
by the deploy-relevant paths, one per line. An empty input is `gate` (fail closed).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence

# Top-level directories whose content can reach the image, the infrastructure or
# the pipeline itself. A path under one of these is never skip-safe, whatever its
# extension (a .md under src/ is package data).
DEPLOY_DIRS: tuple[str, ...] = (".github", "src", "terraform", "deploy", "scripts", "migrations")

# Skip-safe top-level directories (the image never copies them; .dockerignore).
SAFE_DIRS: tuple[str, ...] = ("docs", ".claude", "tests")

SAFE_MARKDOWN_SUFFIX = ".md"
SAFE_TOP_LEVEL_PREFIX = "LICENSE"


def _is_safe(path: str) -> bool:
    if path.startswith("/") or ".." in path.split("/"):
        return False
    top, _, rest = path.partition("/")
    if rest and top in DEPLOY_DIRS:
        return False
    if rest and top in SAFE_DIRS:
        return True
    if not rest and top.startswith(SAFE_TOP_LEVEL_PREFIX):
        return True
    return path.endswith(SAFE_MARKDOWN_SUFFIX)


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
