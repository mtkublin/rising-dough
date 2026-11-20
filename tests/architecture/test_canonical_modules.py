# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""S1: the canonical-modules registry (``canonical_modules.toml``) is well-formed and honest.

* statuses: ``exists`` (resolves, zero banned copies left), ``exists-migrating`` (resolves, copies remain, needs a
  ``migration_task``), ``target`` (not extracted; needs ``interim`` and ``migration_task``). A row may be ``exists``
  only when no banned-copy violation (G6 ``banned-name``) is attributable to its concept (T-Q16: an agent flipped
  ``target`` to ``exists`` after creating the module and leaving four copies);
* every non-``target`` row imports and resolves its symbol; every row has a finding and an epic;
* when ``CLAUDE.md`` carries a "Canonical modules" section (T-Q15c), it must list every registry concept.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.architecture._ratchet import REPO_ROOT, SRC_ROOT, Violation

REGISTRY = Path(__file__).resolve().parent / "canonical_modules.toml"
STATUSES = {"exists", "exists-migrating", "target"}
TASK_ID = re.compile(r"T-Q\d{3}")
REQUIRED = ("concept", "module", "symbol", "status", "finding", "epic", "search", "banned")


def load_registry(path: Path = REGISTRY) -> list[dict[str, Any]]:
    return list(tomllib.loads(path.read_text(encoding="utf-8"))["row"])


def row_problems(row: dict[str, Any]) -> list[str]:
    """Structural problems of one registry row."""
    name = row.get("concept", "?")
    status = row.get("status")
    problems = [f"{name}: missing {key}" for key in REQUIRED if key not in row]
    if status not in STATUSES:
        problems.append(f"{name}: status must be one of {sorted(STATUSES)}")
    if status in {"exists-migrating", "target"} and not TASK_ID.fullmatch(
        str(row.get("migration_task", ""))
    ):
        problems.append(f"{name}: status {status} needs migration_task = T-Q2xx")
    if status == "target" and not str(row.get("interim", "")).strip():
        problems.append(
            f'{name}: target row needs `interim` (the one public copy to call, or "none - extract via T-Q2xx")'
        )
    return problems


def copy_counts(registry: list[dict[str, Any]], violations: list[Violation]) -> dict[str, int]:
    """Banned-copy (G6 ``banned-name``) violations per registry concept."""
    counts = dict.fromkeys((str(r["concept"]) for r in registry), 0)
    for v in violations:
        if v.rule != "banned-name":
            continue
        for concept in counts:
            if f"({concept})" in v.detail:
                counts[concept] += 1
    return counts


def status_problems(registry: list[dict[str, Any]], counts: dict[str, int]) -> list[str]:
    out: list[str] = []
    for row in registry:
        n = counts.get(str(row["concept"]), 0)
        if row.get("status") == "exists" and n:
            out.append(
                f"{row['concept']}: marked `exists` but {n} banned cop(ies) remain. Set status = "
                '"exists-migrating" with a migration_task, or migrate every copy in the same change.'
            )
        if row.get("status") == "exists-migrating" and not n:
            out.append(f'{row["concept"]}: no copies remain; set status = "exists".')
    return out


def resolve(row: dict[str, Any]) -> bool:
    module = "budget_planner." + str(row["module"]).removesuffix(".py").replace("/", ".")
    return hasattr(importlib.import_module(module), str(row["symbol"]))


def test_registry_rows_are_well_formed() -> None:
    problems = [p for row in load_registry() for p in row_problems(row)]
    assert not problems, "\n".join(problems)


def test_resolvable_rows_resolve() -> None:
    unresolved = [
        r["concept"] for r in load_registry() if r["status"] != "target" and not resolve(r)
    ]
    assert not unresolved, (
        f"canonical_modules.toml rows not marked `target` do not resolve: {unresolved}. "
        "Fix the row or flip it back to `target` (ADR-0130 section 3)."
    )
    for row in load_registry():
        if row["status"] != "target":
            assert (SRC_ROOT / row["module"]).is_file(), row["concept"]


def test_target_row_that_now_exists_must_flip() -> None:
    stale = [
        r["concept"]
        for r in load_registry()
        if r["status"] == "target" and (SRC_ROOT / r["module"]).is_file() and resolve(r)
    ]
    assert not stale, (
        f"rows still `target` although module and symbol exist: {stale}. "
        'Set status = "exists" (zero copies) or "exists-migrating".'
    )


def test_exists_requires_zero_banned_copies() -> None:
    collect = importlib.import_module(
        "tests.architecture.test_banned_patterns"
    ).collect  # circular at top level

    registry = load_registry()
    problems = status_problems(registry, copy_counts(registry, collect()))
    assert not problems, "\n" + "\n".join(problems)


def test_claude_md_table_covers_registry() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if "Canonical modules" not in text:
        pytest.skip("CLAUDE.md has no Canonical modules table yet (T-Q15c)")
    missing = [r["concept"] for r in load_registry() if r["concept"] not in text]
    assert not missing, f"CLAUDE.md Canonical modules table is missing registry rows: {missing}"


def test_registry_detects_malformed_row() -> None:
    assert row_problems({"concept": "x", "status": "maybe"})
    assert row_problems({"concept": "x", "status": "target", "interim": "none"})


def test_status_check_catches_premature_exists() -> None:
    row = {"concept": "Periods", "status": "exists"}
    fake = [Violation("services/budget.py", 1, "banned-name", "def _month_range (Periods)")]
    assert status_problems([row], copy_counts([row], fake))
    assert not status_problems([row], copy_counts([row], []))
    migrating = {"concept": "Periods", "status": "exists-migrating"}
    assert status_problems([migrating], copy_counts([migrating], []))
