# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G27: money scope extension of G6: FX conversion, minor-unit scaling, rounding, formatting and parsing
of amounts only in the canonical modules.

Allowlist: ``allowlists/money_scope.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p08_money.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "money_scope"
TEACH = "G27 money: use domain.money (format/parse/exponent/rounding) and the canonical FX converter; no /100, *100, round() or hand-rolled parsers on money (ADR-0008, ADR-0006, ADR-0130 section 3; Q-005, Q-007, Q-011, Q-023, Q-029, Q-076, epic E11)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p08-money"), rules=lambda r: not r.endswith(":canonical") and r != "float-other"
    )


def test_money_scope_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_money_scope_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {"services/m.py": "def to_minor(amount_minor):\n    return round(amount_minor / 100, 2)\n"}
    )
    hits = [r for r in scanned["p08-money"] if r[1] in {"money-round", "money-scale"}]
    assert hits, "fixture violation not detected by the scanner rule"
