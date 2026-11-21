# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G5: coverage config guard (Q-014): ``[tool.coverage.report] exclude_lines`` equals an approved set.

An unanchored regex such as ``\\.\\.\\.`` silently excludes every line containing an ellipsis from coverage.
The current offender is allowlisted (``allowlists/coverage_config.toml``, Q-014) until its remediation lands.
"""

from __future__ import annotations

import tomllib
from typing import Any

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "coverage_config"
HEADER = "G5 coverage_config: exclude_lines outside the approved set (Q-014; ADR-0130 section 10)."
APPROVED = frozenset(
    {
        "pragma: no cover",
        "raise NotImplementedError",
        "if TYPE_CHECKING:",
        "if __name__ == .__main__.:",
        "@overload",
    }
)
TEACH = (
    "G5 coverage config: exclude_lines may only contain anchored, approved patterns "
    f"{sorted(APPROVED)}. A broad regex hides untested code (Q-014, ADR-0130 section 10)."
)


def violations_for(config: dict[str, Any]) -> list[Violation]:
    report = config.get("tool", {}).get("coverage", {}).get("report", {})
    return [
        Violation("pyproject.toml", 0, pattern, "unapproved coverage exclude pattern")
        for pattern in report.get("exclude_lines", [])
        if pattern not in APPROVED
    ]


def collect() -> list[Violation]:
    return violations_for(tomllib.loads((REPO_ROOT / "pyproject.toml").read_text()))


def meta(_v: Violation) -> tuple[str, str, str, str]:
    return "entry", "Q-014", "E14", ""


def test_coverage_exclude_lines_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_coverage_config_detects_unanchored_pattern() -> None:
    config = {
        "tool": {"coverage": {"report": {"exclude_lines": ["pragma: no cover", "\\.\\.\\."]}}}
    }
    assert [v.rule for v in violations_for(config)] == ["\\.\\.\\."]
