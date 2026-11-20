# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G25: size and complexity ratchet: files over 800 lines, functions over 50 lines, nesting over 4, cyclomatic >= 11.

Allowlist: ``allowlists/size_complexity.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p09_p10_p11_imports_size_suppress.py (p10)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "size_complexity"
TEACH = "G25 size/complexity: split the module or extract focused functions (common coding-style rule: files < 800 lines, functions < 50 lines, nesting <= 4; Q-046, Q-047, Q-048, epic E13)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p10-size"), rules=lambda r: r in {"file>800", "func>50", "nesting>4", "cc>=11"}
    )


def test_size_complexity_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_size_complexity_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "services/big.py": "def f(x):\n"
            + "".join(f"    x = x + {i}\n" for i in range(60))
            + "    return x\n"
        }
    )
    hits = [r for r in scanned["p10-size"] if r[1] == "func>50"]
    assert hits, "fixture violation not detected by the scanner rule"
