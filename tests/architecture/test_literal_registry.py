# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G19: literal registry: domain strings (HTMX events, headers, currencies, timezones, enum values) and
repeated literals live only in their defining module.

Allowlist: ``allowlists/literals.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p13_other.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "literals"
TEACH = "G19 literals: import the constant from its defining module (web/htmx.py, config.py, domain/enums.py) instead of repeating the string (Q-038, epic E03)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p13-other"), rules=lambda r: r in {"domain-literal", "repeated-literal"}
    )


def test_literals_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_literals_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan({"services/lit.py": 'def f():\n    return "Europe/Warsaw"\n'})
    hits = [r for r in scanned["p13-other"] if r[1] == "domain-literal"]
    assert hits, "fixture violation not detected by the scanner rule"
