# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G18: clone ratchet: structurally identical function bodies and same-name private helpers in several modules.

Allowlist: ``allowlists/clones.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p01_dry.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "clones"
TEACH = "G18 clones: extract the shared helper (repositories/_shared for CRUD shapes) and import it instead of copying the body (ADR-0130 section 1; epics E02/E03)."


def collect() -> list[Violation]:
    return violations_from_rows(rows("p01-clones-ast")) + violations_from_rows(
        rows("p01-same-name"), keep=lambda _loc, _r, detail: detail.startswith("_")
    )


def test_clones_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_clones_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "services/a.py": "def _helper(x):\n    y = x + 1\n    z = y * 2\n    w = z - 3\n    return w\n",
            "services/b.py": "def _helper(q):\n    r = q + 1\n    s = r * 2\n    t = s - 3\n    return t\n",
        }
    )
    hits = [r for r in scanned["p01-same-name"] if r[2].startswith("_helper")]
    assert hits, "fixture violation not detected by the scanner rule"


def test_clones_ignores_dunder_same_name(synthetic_scan: SyntheticScan) -> None:
    """Protocol dunders (``__call__``, ``__post_init__``) share names by contract, not by copy-paste."""
    body = "        y = x + 1\n        z = y * 2\n        return z\n"
    scanned = synthetic_scan(
        {
            "services/a.py": f"class A:\n    def __call__(self, x):\n{body}    def __post_init__(self, x):\n{body}",
            "services/b.py": f"class B:\n    def __call__(self, x):\n{body}    def __post_init__(self, x):\n{body}",
        }
    )
    assert not [r for r in scanned["p01-same-name"] if "__" in r[2]]
