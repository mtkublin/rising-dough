# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Exact-ratchet allowlist helper shared by every architecture guard (ADR-0130 section 2).

Each guard owns one TOML file ``tests/architecture/allowlists/<guard>.toml``::

    guard = "sql_sites"

    [[entry]]            # burn-down debt: must reach zero
    path = "src/budget_planner/services/accounts.py"
    rule = "sql-exec"    # optional sub-rule, "" when the guard has a single rule
    count = 2
    finding = "Q-074"    # Q-id or inventory id
    epic = "E10"         # remediation epic (E01..E16)
    owner = "T-UR08"     # redesign carve-out only (template_logic.toml): the T-UR task that deletes it

    [[permanent]]        # justified, reason required, recorded in an ADR-0130 amendment
    ...
    reason = "PRAGMA at connection setup"

    [[framework]]        # framework-imposed idiom (operator decision 2026-11-20); not counted toward zero
    ...
    reason = "Starlette BaseHTTPMiddleware"

The guard fails when a (path, rule) count **rises** (new violation) and when it **falls**
(the allowlist must shrink with the fix). Counts, not line numbers, so unrelated edits do not
break the guard. A path with no entry has an allowance of zero, so new code starts clean.
"""

from __future__ import annotations

import ast
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "budget_planner"
ALLOWLIST_DIR = Path(__file__).resolve().parent / "allowlists"
ADR = "ADR-0130"
TABLES = ("entry", "permanent", "framework")


@dataclass(frozen=True)
class Violation:
    """One detected violation. ``path`` is repo-relative posix; ``rule`` may be empty."""

    path: str
    line: int
    rule: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Entry:
    path: str
    rule: str
    count: int
    table: str
    finding: str
    epic: str
    reason: str
    owner: str = ""


def violations_from_rows(
    rows: Iterable[tuple[str, str, str]],
    *,
    rules: Callable[[str], bool] = lambda _rule: True,
    keep: Callable[[str, str, str], bool] = lambda _loc, _rule, _detail: True,
) -> list[Violation]:
    """Convert scanner rows ``("path:line", rule, detail)`` into violations, filtered by rule."""
    out: list[Violation] = []
    for loc, rule, detail in rows:
        if not rules(rule) or not keep(loc, rule, detail):
            continue
        path, _, line = loc.rpartition(":")
        out.append(Violation(path, int(line) if line.isdigit() else 0, rule, detail))
    return out


@cache
def parse_file(path: Path) -> ast.Module:
    """Parse a source file once per process."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def src_files(*subdirs: str) -> list[Path]:
    """Python files under ``src/budget_planner`` (optionally restricted to sub-directories)."""
    roots = [SRC_ROOT / s for s in subdirs] if subdirs else [SRC_ROOT]
    return sorted(p for r in roots for p in r.rglob("*.py") if "__pycache__" not in p.parts)


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def allowlist_path(guard: str) -> Path:
    return ALLOWLIST_DIR / f"{guard}.toml"


def load_entries(guard: str, directory: Path | None = None) -> list[Entry]:
    """Read every table of a guard's allowlist."""
    path = (directory or ALLOWLIST_DIR) / f"{guard}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[Entry] = []
    for table in TABLES:
        for raw in data.get(table, []):
            entries.append(
                Entry(
                    path=raw["path"],
                    rule=raw.get("rule", ""),
                    count=int(raw["count"]),
                    table=table,
                    finding=raw.get("finding", ""),
                    epic=raw.get("epic", ""),
                    reason=raw.get("reason", ""),
                    owner=raw.get("owner", ""),
                )
            )
    return entries


def _allowed_counts(entries: Iterable[Entry]) -> Counter[tuple[str, str]]:
    allowed: Counter[tuple[str, str]] = Counter()
    for e in entries:
        allowed[(e.path, e.rule)] += e.count
    return allowed


def ratchet_problems(
    guard: str,
    violations: Iterable[Violation],
    *,
    entries: list[Entry] | None = None,
) -> list[str]:
    """Compare actual per-(path, rule) counts with the allowlist; return human messages."""
    found = list(violations)
    actual: Counter[tuple[str, str]] = Counter((v.path, v.rule) for v in found)
    allowed = _allowed_counts(entries if entries is not None else load_entries(guard))
    where = f"tests/architecture/allowlists/{guard}.toml"
    problems: list[str] = []
    for key in sorted(set(actual) | set(allowed)):
        now, ok = actual.get(key, 0), allowed.get(key, 0)
        path, rule = key
        label = f"{path} [{rule}]" if rule else path
        if now > ok:
            sites = ", ".join(str(v.line) for v in found if (v.path, v.rule) == key)
            problems.append(
                f"NEW violation: {label} has {now}, allowed {ok} (lines {sites}). "
                f"Fix the code; do not raise the allowance ({ADR} section 1.3: a new entry needs an ADR amendment)."
            )
        elif now < ok:
            problems.append(
                f"FIXED, allowlist not lowered: {label} has {now}, allowed {ok}. "
                f"Edit {where}: set count = {now}"
                f"{' (delete the entry)' if now == 0 else ''} ({ADR} section 2: the allowlist must equal the truth)."
            )
    return problems


def assert_ratchet(guard: str, violations: Iterable[Violation], teach: str) -> None:
    """Fail with a teaching message when the actual counts differ from the allowlist."""
    problems = ratchet_problems(guard, violations)
    assert not problems, "\n" + teach + "\n" + "\n".join(f"  - {p}" for p in problems)


def framework_count(guard: str) -> int:
    return sum(e.count for e in load_entries(guard) if e.table == "framework")


def burn_down_count(guard: str) -> int:
    return sum(e.count for e in load_entries(guard) if e.table == "entry")


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump_allowlist(guard: str, header: str, entries: Iterable[Entry], extra: str = "") -> str:
    """Render an allowlist file (sorted, deterministic). Used by the generator and tests."""
    lines = [f"# {line}" if line else "#" for line in header.strip().splitlines()]
    lines += ["", f"guard = {_quote(guard)}", ""]
    if extra:
        lines += [extra.rstrip(), ""]
    for table in TABLES:
        for e in sorted((x for x in entries if x.table == table), key=lambda x: (x.path, x.rule)):
            lines.append(f"[[{table}]]")
            lines.append(f"path = {_quote(e.path)}")
            if e.rule:
                lines.append(f"rule = {_quote(e.rule)}")
            lines.append(f"count = {e.count}")
            lines.append(f"finding = {_quote(e.finding)}")
            if e.epic:
                lines.append(f"epic = {_quote(e.epic)}")
            if e.reason:
                lines.append(f"reason = {_quote(e.reason)}")
            if e.owner:
                lines.append(f"owner = {_quote(e.owner)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
