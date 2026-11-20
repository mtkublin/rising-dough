# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G1 support: direct import-contract violations and import cycles (the import-linter config is owned by T-Q15b;
this ratchet pins the exact current pairs so ``ignore_imports`` can be generated from it).

Allowlist: ``allowlists/layering.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p09_p10_p11_imports_size_suppress.py (p09)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "layering"
TEACH = "G1 layering: routers call services, never repositories; web does not import db except the connection dependency; repositories do not import services (ADR-0130 section 5; Q-045, Q-047, Q-074, epics E08/E12)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p09-layering"), rules=lambda r: r.startswith("contract:") or r == "cycle"
    )


def test_layering_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_layering_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "repositories/a.py": "x = 1\n",
            "services/b.py": "x = 1\n",
            "web/routers/r.py": "from budget_planner.repositories import a\n",
        }
    )
    hits = [r for r in scanned["p09-layering"] if r[1] == "contract:routers-not-repositories"]
    assert hits, "fixture violation not detected by the scanner rule"
