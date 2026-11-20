# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G10: tests never reference the production database (CLAUDE.md "data/budget.sqlite is production").

* no ``budget.sqlite`` in ``tests/`` outside an allowlist of tmp-path text assertions
  (``allowlists/prod_db_refs.toml``);
* the autouse session tripwire in ``tests/conftest.py`` makes ``sqlite3.connect`` raise for the prod path and the
  suite pins ``BUDGET_ENV=test`` unconditionally.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import pytest

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "prod_db_refs"
HEADER = "G10 prod_db_refs: tests mentioning budget.sqlite (tmp_path file names and text assertions only)."
NEEDLE = re.compile(r"budget\.sqlite")
TESTS = REPO_ROOT / "tests"
TEACH = (
    "G10 prod DB: tests must use tmp_path databases or the migrated template; never name data/budget.sqlite "
    "(CLAUDE.md Databases; Q-060)."
)


def scan_text(path: str, text: str) -> list[Violation]:
    return [
        Violation(path, i, "", line.strip()[:80])
        for i, line in enumerate(text.splitlines(), 1)
        if NEEDLE.search(line)
    ]


def collect() -> list[Violation]:
    found: list[Violation] = []
    for path in sorted(TESTS.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("tests/architecture/"):
            continue
        found += scan_text(rel, path.read_text(encoding="utf-8"))
    return found


def meta(_v: Violation) -> tuple[str, str, str, str]:
    return (
        "permanent",
        "Q-060",
        "",
        "file name under tmp_path or a text assertion, never the repo data/ database",
    )


def test_prod_db_refs_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_prod_db_refs_detects_fixture() -> None:
    assert scan_text("tests/x.py", 'db = Path("data/budget.sqlite")\n')


def test_budget_env_is_pinned_to_test() -> None:
    assert os.environ["BUDGET_ENV"] == "test"


def test_tripwire_blocks_the_production_database() -> None:
    with pytest.raises(RuntimeError, match="production database"):
        sqlite3.connect(REPO_ROOT / "data" / "budget.sqlite")
    with pytest.raises(RuntimeError, match="production database"):
        sqlite3.connect(REPO_ROOT / "data" / ".." / "data" / "budget.sqlite")


def test_tripwire_allows_memory_and_tmp_databases(tmp_path: Path) -> None:
    sqlite3.connect(":memory:").close()
    sqlite3.connect(tmp_path / "budget.sqlite").close()
