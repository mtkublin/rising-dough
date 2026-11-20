# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G4: suppression hygiene (ADR-0130 section 6).

(a) every inline ``# noqa`` / ``# type: ignore`` / ``# nosec`` / ``# pragma: no cover`` in ``src/`` carries a reason
on the same line (a comment above does not count); (b) per-code ceilings ratchet down for the bulk codes.

Allowlist: ``allowlists/suppressions.toml`` (reason-less sites per file, plus the ``[ceilings]`` table).
"""

from __future__ import annotations

import tomllib
from collections import Counter

from tests.architecture._ratchet import (
    Violation,
    allowlist_path,
    assert_ratchet,
    violations_from_rows,
)
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "suppressions"
HEADER = "G4 suppressions: inline suppressions without a same-line reason, plus exact per-code ceilings (ADR-0130 section 6)."
CEILING_CODES = ("PLC0415", "PLR0917", "DTZ011")
TEACH = (
    "G4 suppressions: add a reason on the same line (`# noqa: CODE -- why`), or better remove the need for the "
    "suppression. No new suppression without a reason and, where a guard exists, an ADR amendment (ADR-0130 section 6; "
    "Q-047, Q-048, epic E14)."
)


def _reasonless(_loc: str, rule: str, detail: str) -> bool:
    return rule.startswith("suppress:") and "reason-same-line=NO" in detail


def collect() -> list[Violation]:
    return violations_from_rows(rows("p11-suppressions"), keep=_reasonless)


def ceiling_counts(scanned: list[tuple[str, str, str]]) -> dict[str, int]:
    """Number of inline ``noqa`` suppressions per bulk ruff code."""
    counts: Counter[str] = Counter()
    for _loc, rule, detail in scanned:
        if rule != "suppress:noqa":
            continue
        codes = detail.split(" |")[0]
        counts.update(c.strip() for c in codes.split(",") if c.strip() in CEILING_CODES)
    return {code: counts.get(code, 0) for code in CEILING_CODES}


def meta(_v: Violation) -> tuple[str, str, str, str]:
    return "entry", "Q-048", "E14", ""


def allowlist_extra() -> str:
    body = "\n".join(
        f"{code} = {n}" for code, n in ceiling_counts(rows("p11-suppressions")).items()
    )
    return (
        "# Inline noqa count per bulk code: exact ratchet, must reach zero "
        "(PLC0415: E12, PLR0917: E13, DTZ011: E07).\n[ceilings]\n" + body
    )


def test_suppressions_have_reasons_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_suppression_ceilings_are_exact() -> None:
    allowed = tomllib.loads(allowlist_path(GUARD).read_text())["ceilings"]
    actual = ceiling_counts(rows("p11-suppressions"))
    assert actual == allowed, (
        "\nG4 ceilings: inline suppression counts must equal tests/architecture/allowlists/suppressions.toml [ceilings] "
        f"(ADR-0130 section 6). actual={actual} allowed={allowed}. Lower the ceiling when you remove suppressions; "
        "never raise it."
    )


def test_suppressions_detects_bare_noqa(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan({"services/s.py": "import os  # noqa: F401\nx = 1  # type: ignore\n"})
    bare = [r for r in scanned["p11-suppressions"] if "reason-same-line=NO" in r[2]]
    assert len(bare) == 2
