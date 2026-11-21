# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G20: functional-first style and immutability (ADR-0021): no ad-hoc classes, no mutable module state,
no ``global``, no hidden caches, no argument or module mutation.

Allowlist: ``allowlists/functional_first.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p02_functional.py, p03_immutability.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "functional_first"
TEACH = "G20 functional-first: use frozen dataclasses / tuples / MappingProxyType, pass state explicitly, do not mutate arguments (ADR-0021, ADR-0130; Q-074, epics E04/E05/E07). Framework idioms live in the [[framework]] table."


def collect() -> list[Violation]:
    def _accepted(_loc: str, rule: str, detail: str) -> bool:
        # frozen sentinels, the app entry point, loggers and typing helpers are accepted (inventory section 3)
        return rule != "module-singleton" or detail.startswith("router = APIRouter")

    return violations_from_rows(rows("p02-functional"), keep=_accepted) + violations_from_rows(
        rows("p03-immutability")
    )


def test_functional_first_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_functional_first_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {"services/s.py": "_CACHE = {}\n\n\ndef f():\n    global _CACHE\n    return 1\n"}
    )
    hits = [r for r in scanned["p02-functional"] if r[1] in {"mutable-constant", "global-stmt"}]
    assert hits, "fixture violation not detected by the scanner rule"
