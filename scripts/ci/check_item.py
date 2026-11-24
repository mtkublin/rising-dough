"""Executable Definition of Done for one orchestrated work item (ADR-0150 §4, T-Q326).

Checks the item branch ``wi/<work>/<ID>`` against the work branch, mechanically:
the branch is ahead, every changed file is owned, scribe hotspots are untouched,
commit subjects carry the item id, allowlist totals did not rise, a template or
CSS change adds an audit record. It also lists, as WARN lines for the reviewer,
added suppressions and new top-level definitions (canonical-concept names flagged).

Output: one ``PASS|FAIL|WARN <check>: <detail>`` line per finding. Exit 1 on any FAIL.

Usage: check_item.py --item <ID> [--work <branch>] [--owned <glob> ...]
       (--work defaults to the current branch)
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess  # nosec B404
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass

HOTSPOTS = ("docs/CHANGELOG.md", "docs/adr/README.md", "docs/plans/*/tasks.md")
ALLOWLISTS = "tests/architecture/allowlists/"
FRONTEND = ("src/budget_planner/web/templates/*", "src/budget_planner/web/static/*.css")
AUDITS = "docs/audits/*.md"
_SUBJECT_TYPES = "feat|fix|docs|refactor|test|chore|ci|perf|build|style|revert"
_SUPPRESSION = re.compile(r"#\s*(noqa|type:\s*ignore|nosec|pragma:\s*no cover)")
_TOP_DEF = re.compile(r"^(?:async\s+)?(?:def|class)\s+(\w+)")
# Canonical modules concepts (CLAUDE.md table); a match only flags, the reviewer decides.
_CANONICAL = re.compile(
    r"convert|month|period|today|now|sign|parse|total|fx|rate|money|format|round|minor|major|balance|fortune|occurrence|tier",
    re.IGNORECASE,
)
_CANONICAL_TAG = " (canonical concept: check the Canonical modules table)"


@dataclass(frozen=True)
class Finding:
    level: str  # PASS, FAIL or WARN
    check: str
    detail: str = ""

    def line(self) -> str:
        return f"{self.level} {self.check}" + (f": {self.detail}" if self.detail else "")


def _matches(path: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def check_ahead(ahead: int) -> Finding:
    if ahead > 0:
        return Finding("PASS", "ahead", f"{ahead} commit(s)")
    return Finding("FAIL", "ahead", "the item branch has no commits beyond the work branch")


def check_owned(changed: Sequence[str], owned: Sequence[str]) -> Finding:
    if not owned:
        return Finding("WARN", "owned", "no --owned globs given; ownership not checked")
    stray = [p for p in changed if not _matches(p, owned)]
    if stray:
        return Finding("FAIL", "owned", "not owned: " + ", ".join(stray))
    return Finding("PASS", "owned")


def check_hotspots(changed: Sequence[str], owned: Sequence[str]) -> Finding:
    """Scribe hotspots may change only when the brief lists the exact path as owned."""
    touched = [p for p in changed if _matches(p, HOTSPOTS) and p not in owned]
    if touched:
        detail = "scribe-owned, not listed literally in --owned: " + ", ".join(touched)
        return Finding("FAIL", "hotspots", detail)
    return Finding("PASS", "hotspots")


def check_subjects(subjects: Sequence[str], item: str) -> Finding:
    pattern = re.compile(rf"^({_SUBJECT_TYPES})\({re.escape(item)}[^)]*\)!?: \S")
    bad = [s for s in subjects if not pattern.match(s)]
    if bad:
        return Finding("FAIL", "subjects", f"not '<type>({item}): ...': " + " | ".join(bad))
    return Finding("PASS", "subjects")


def allowlist_total(text: str) -> int:
    """Sum of ``count`` (1 when absent) over every table array of an allowlist file."""
    if not text.strip():
        return 0
    total = 0
    for value in tomllib.loads(text).values():
        if isinstance(value, list):
            total += sum(int(row.get("count", 1)) for row in value if isinstance(row, dict))
    return total


def check_allowlists(totals: dict[str, tuple[int, int]]) -> Finding:
    """``totals`` maps an allowlist path to (work branch total, item branch total)."""
    risen = [f"{p} {base}->{head}" for p, (base, head) in sorted(totals.items()) if head > base]
    if risen:
        return Finding("FAIL", "allowlists", "rose: " + ", ".join(risen))
    fallen = [f"{p} {base}->{head}" for p, (base, head) in sorted(totals.items()) if head < base]
    return Finding("PASS", "allowlists", ("shrank: " + ", ".join(fallen)) if fallen else "")


def check_audit(changed: Sequence[str], added: Sequence[str]) -> Finding:
    frontend = [p for p in changed if _matches(p, FRONTEND)]
    if not frontend:
        return Finding("PASS", "audit", "no template or CSS change")
    if any(_matches(p, (AUDITS,)) for p in added):
        return Finding("PASS", "audit")
    detail = "template/CSS changed but no docs/audits/*.md added: " + ", ".join(frontend)
    return Finding("FAIL", "audit", detail)


def added_lines(diff: str) -> list[tuple[str, str]]:
    """(path, text) for each added line of a unified diff with ``-U0``."""
    out: list[tuple[str, str]] = []
    path = ""
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else ""
        elif raw.startswith("+") and path:
            out.append((path, raw[1:]))
    return out


def suppression_findings(lines: Sequence[tuple[str, str]]) -> list[Finding]:
    return [
        Finding("WARN", "suppression", f"{path}: {text.strip()}")
        for path, text in lines
        if path.endswith(".py") and _SUPPRESSION.search(text)
    ]


def definition_findings(lines: Sequence[tuple[str, str]]) -> list[Finding]:
    found: list[Finding] = []
    for path, text in lines:
        if not (path.startswith("src/") and path.endswith(".py")):
            continue
        match = _TOP_DEF.match(text)
        if match:
            name = match.group(1)
            tag = _CANONICAL_TAG if _CANONICAL.search(name) else ""
            found.append(Finding("WARN", "new-def", f"{path}: {name}{tag}"))
    return found


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607  # nosec B603 B607 (fixed git argv, no shell)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def _show(ref: str, path: str) -> str:
    try:
        return _git("show", f"{ref}:{path}")
    except RuntimeError:
        return ""  # the file does not exist on that side


def run(item: str, work: str, owned: Sequence[str]) -> list[Finding]:
    branch = f"wi/{work}/{item}"
    base = _git("merge-base", work, branch).strip()
    rng = f"{base}..{branch}"
    changed = _git("diff", "--name-only", base, branch).split()
    added = _git("diff", "--name-only", "--diff-filter=A", base, branch).split()
    subjects = _git("log", "--no-merges", "--format=%s", rng).splitlines()
    ahead = int(_git("rev-list", "--count", f"{work}..{branch}").strip())
    totals = {
        p: (allowlist_total(_show(work, p)), allowlist_total(_show(branch, p)))
        for p in changed
        if p.startswith(ALLOWLISTS) and p.endswith(".toml")
    }
    lines = added_lines(_git("diff", "-U0", base, branch, "--", "*.py"))
    return [
        check_ahead(ahead),
        check_owned(changed, owned),
        check_hotspots(changed, owned),
        check_subjects(subjects, item),
        check_allowlists(totals),
        check_audit(changed, added),
        *suppression_findings(lines),
        *definition_findings(lines),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--item", required=True)
    parser.add_argument("--work", default="")
    parser.add_argument("--owned", nargs="*", default=[])
    args = parser.parse_args(argv)
    work = args.work or _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    try:
        findings = run(args.item, work, args.owned)
    except RuntimeError as exc:
        print(f"FAIL git: {exc}")
        return 1
    for finding in findings:
        print(finding.line())
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
