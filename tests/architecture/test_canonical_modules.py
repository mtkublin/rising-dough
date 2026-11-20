# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""S1: the canonical-modules registry (``canonical_modules.toml``) is well-formed and honest.

* every ``exists`` row imports and resolves its symbol; every ``target`` row has a finding and an epic;
* when ``CLAUDE.md`` carries a "Canonical modules" section (T-Q15c), it must list every registry concept.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.architecture._ratchet import REPO_ROOT, SRC_ROOT

REGISTRY = Path(__file__).resolve().parent / "canonical_modules.toml"
REQUIRED = ("concept", "module", "symbol", "status", "finding", "epic", "search", "banned")


def load_registry(path: Path = REGISTRY) -> list[dict[str, Any]]:
    return list(tomllib.loads(path.read_text(encoding="utf-8"))["row"])


def row_problems(row: dict[str, Any]) -> list[str]:
    """Structural problems of one registry row."""
    problems = [f"{row.get('concept', '?')}: missing {key}" for key in REQUIRED if key not in row]
    if row.get("status") not in {"exists", "target"}:
        problems.append(f"{row.get('concept', '?')}: status must be exists or target")
    return problems


def resolve(row: dict[str, Any]) -> bool:
    module = "budget_planner." + str(row["module"]).removesuffix(".py").replace("/", ".")
    return hasattr(importlib.import_module(module), str(row["symbol"]))


def test_registry_rows_are_well_formed() -> None:
    problems = [p for row in load_registry() for p in row_problems(row)]
    assert not problems, "\n".join(problems)


def test_exists_rows_resolve_and_target_rows_have_a_home() -> None:
    unresolved = [
        r["concept"] for r in load_registry() if r["status"] == "exists" and not resolve(r)
    ]
    assert not unresolved, (
        f"canonical_modules.toml rows marked `exists` do not resolve: {unresolved}. "
        "Fix the row or flip it back to `target` (ADR-0130 section 3)."
    )
    for row in load_registry():
        if row["status"] == "exists":
            assert (SRC_ROOT / row["module"]).is_file(), row["concept"]


def test_target_row_that_now_exists_must_flip_to_exists() -> None:
    stale = [
        r["concept"]
        for r in load_registry()
        if r["status"] == "target" and (SRC_ROOT / r["module"]).is_file() and resolve(r)
    ]
    assert not stale, (
        f'rows still `target` although module and symbol exist: {stale}. Set status = "exists".'
    )


def test_claude_md_table_covers_registry() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if "Canonical modules" not in text:
        pytest.skip("CLAUDE.md has no Canonical modules table yet (T-Q15c)")
    missing = [r["concept"] for r in load_registry() if r["concept"] not in text]
    assert not missing, f"CLAUDE.md Canonical modules table is missing registry rows: {missing}"


def test_registry_detects_malformed_row() -> None:
    assert row_problems({"concept": "x", "status": "maybe"})
