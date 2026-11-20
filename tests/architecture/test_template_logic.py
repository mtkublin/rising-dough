# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G9: template-logic ratchet: arithmetic, float, scaling, formatting, ``{% set %}`` and hard-coded currency
in Jinja templates. New templates start at zero (ADR-0107 redesign).

Allowlist: ``allowlists/template_logic.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p12_templates.py`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "template_logic"
TEACH = "G9 template logic: compute in the service / view model and print the value; format money through the money filter (requirements 3.3; Q-011, Q-039, Q-070, epic E16)."


def collect() -> list[Violation]:
    return violations_from_rows(rows("p12-templates"))


def test_template_logic_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_template_logic_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {"web/templates/t.html": "{% set pct = spent / budget * 100 %}<p>{{ pct }}</p>\n"}
    )
    hits = [r for r in scanned["p12-templates"] if r[1] in {"tpl-set", "tpl-arith", "tpl-scale"}]
    assert hits, "fixture violation not detected by the scanner rule"
