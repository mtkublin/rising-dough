# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G22: pure layers (ADR-0021 as amended by ADR-0130 section 5). Services may use ``logging`` (operator
decision 2026-11-20); network, clock, entropy, settings reads and config imports are violations.

Allowlist: ``allowlists/purity.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p04_p07_effects_clock.py (p04)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "purity"
TEACH = "G22 purity: services and domain take the clock, settings, rates and entropy as arguments; effects live in repositories, clock.py and adapters (ADR-0130 section 5; Q-007, Q-031, epics E06/E07)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p04-side-effects"),
        rules=lambda r: r != "eff-log",  # logging in services is permitted (operator decision)
        keep=lambda _loc, _r, detail: detail != "[services] imports logging",
    )


def test_purity_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_purity_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {"domain/d.py": "import httpx\n\n\ndef f():\n    return httpx.Client(timeout=1)\n"}
    )
    hits = [r for r in scanned["p04-side-effects"] if r[1] in {"eff-net", "eff-import"}]
    assert hits, "fixture violation not detected by the scanner rule"


def test_purity_forbids_bcrypt_in_services(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan({"services/s.py": "import bcrypt\n\n\ndef f():\n    return bcrypt\n"})
    hits = [r for r in scanned["p04-side-effects"] if r[1] == "eff-import" and "bcrypt" in r[2]]
    assert hits, "bcrypt import in services/ must be an eff-import violation (T-Q291)"
