# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G23: thin web, fat services. Router functions carry no logic and routers hold no helper functions.

Allowlist: ``allowlists/thin_router.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p05_p06_web_repo.py (p05)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "thin_router"
TEACH = "G23 thin router: move arithmetic, branching on domain values, SQL and transactions into services/<page>.py (create it if missing) returning a frozen view model; copy the pattern of services/today.py (router: parse params, call service, render). See CLAUDE.md code conventions (Q-003, Q-004, Q-010, Q-024, Q-028, epics E08/E09)."


def collect() -> list[Violation]:
    return violations_from_rows(rows("p05-thin-web"))


def test_thin_router_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_thin_router_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "web/routers/r.py": 'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/x")\ndef x(a: int, b: int):\n    return {"v": a * b - 3}\n'
        }
    )
    hits = [r for r in scanned["p05-thin-web"] if r[1] == "logic-in-router"]
    assert hits, "fixture violation not detected by the scanner rule"
