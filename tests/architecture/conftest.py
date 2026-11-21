# Guard docstrings and teaching messages are prose; long lines are intentional.
"""Fixtures for the architecture guards: synthetic trees for fixture-violation self-tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.architecture._scan import scan_synthetic

SyntheticScan = Callable[[dict[str, str]], dict[str, list[tuple[str, str, str]]]]


@pytest.fixture
def synthetic_scan(tmp_path: Path) -> SyntheticScan:
    """Write ``{relative path under src/budget_planner: source}`` and run every scanner on it."""

    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")

    def run(files: dict[str, str]) -> dict[str, list[tuple[str, str, str]]]:
        for rel, text in files.items():
            target = tmp_path / "src" / "budget_planner" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return scan_synthetic(tmp_path)

    return run
