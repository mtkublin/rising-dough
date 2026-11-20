# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G26: error handling and hygiene: no swallowed or broad exceptions, no ``assert`` or ``print`` in src, no ``Any``
in signatures.

Allowlist: ``allowlists/hygiene.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p13_other.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "hygiene"
TEACH = "G26 hygiene: handle or log exceptions, raise typed errors instead of assert, use logging instead of print, type signatures precisely (common coding-style error-handling rules; Q-073, epic E15)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p13-other"),
        rules=lambda r: (
            r in {"silent-except", "broad-except", "assert-in-src", "print-call", "any-annotation"}
        ),
    )


def test_hygiene_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_hygiene_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "services/h.py": "def f():\n    try:\n        return 1\n    except Exception:\n        pass\n    assert True\n    print(1)\n"
        }
    )
    hits = [
        r
        for r in scanned["p13-other"]
        if r[1] in {"silent-except", "broad-except", "assert-in-src", "print-call"}
    ]
    assert hits, "fixture violation not detected by the scanner rule"
