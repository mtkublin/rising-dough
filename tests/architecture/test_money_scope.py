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


def test_money_round_ignores_calendar_arithmetic(synthetic_scan: SyntheticScan) -> None:
    """T-Q16: `//` in domain/periods.py is month arithmetic; an agent dodged the false positive with divmod."""
    source = "def shift(a, b):\n    return a // b\n"
    scanned = synthetic_scan({"domain/periods.py": source, "services/other.py": source})
    hits = {(r[0].split(":")[0].rsplit("/", 1)[-1], r[1]) for r in scanned["p08-money"]}
    assert ("other.py", "money-round") in hits
    assert ("periods.py", "money-round") not in hits


def _fx_hits(scanned: dict[str, list[tuple[str, str, str]]]) -> set[tuple[str, str]]:
    return {(r[0].split(":")[0].rsplit("/", 1)[-1], r[1]) for r in scanned["p08-money"]}


def test_fx_def_flags_conversion_under_a_neutral_name(synthetic_scan: SyntheticScan) -> None:
    """T-Q293: the rule keys on rate arithmetic, not on the function name."""
    source = (
        "def adjust(amount_minor, quote):\n"
        "    return amount_minor * quote.mid\n"
        "\n"
        "def settle(amount_minor, fx_rate):\n"
        "    return (amount_minor / fx_rate).quantize(1)\n"
    )
    scanned = synthetic_scan({"services/neutral.py": source, "services/fx.py": source})
    hits = _fx_hits(scanned)
    assert ("neutral.py", "fx-def") in hits
    assert ("fx.py", "fx-def") not in hits
    assert ("fx.py", "fx-def:canonical") in hits


def test_fx_def_flags_division_by_a_rate_lookup_and_rate_quantize(
    synthetic_scan: SyntheticScan,
) -> None:
    source = (
        "def back(conn, amount_minor):\n"
        "    return amount_minor / conn.latest_rate('EUR')\n"
        "\n"
        "def snap(value, fx_rate):\n"
        "    return value.quantize(fx_rate)\n"
    )
    scanned = synthetic_scan({"services/other.py": source})
    details = [r[2] for r in scanned["p08-money"] if r[1] == "fx-def"]
    assert len(details) == 2, details


def test_fx_def_ignores_fx_named_functions_without_rate_arithmetic(
    synthetic_scan: SyntheticScan,
) -> None:
    source = (
        "def formula_fx(conn, user_id):\n"
        "    return conn, user_id\n"
        "\n"
        "def rates_freshness(rows):\n"
        "    return len(rows) * 2\n"
        "\n"
        "def retry_after(rate_limit, window):\n"
        "    return window / rate_limit\n"
        "\n"
        "def get_formula_fx():\n"
        "    return None\n"
    )
    scanned = synthetic_scan({"services/names.py": source})
    assert not [r for r in scanned["p08-money"] if r[1].startswith("fx-")]
