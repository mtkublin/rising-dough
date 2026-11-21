# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G7: the differential invariants (``tests/integration/invariants/``) and their strict xfails (ADR-0130 section 3).

Every ``xfail`` there must be ``strict=True`` and cite an open Q-id; the set of (file, Q-id) markers is an exact ratchet
(``allowlists/invariants.toml``). Fixing a finding makes its invariant XPASS, which fails the run (strict), so the fix
must remove the marker, and this registry then requires the allowlist entry to be deleted.
"""

from __future__ import annotations

import re

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "invariants"
HEADER = "G7 invariants: strict xfails of the differential invariants, one entry per (file, open Q-id) (Q-013)."
INVARIANTS = REPO_ROOT / "tests" / "integration" / "invariants"
XFAIL = re.compile(r"pytest\.mark\.xfail\(([^)]*)\)", re.S)
REASON_QID = re.compile(r'reason="(Q-\d{3})\b')
TEACH = (
    "G7 invariants: an invariant that fails because of an open finding is a strict xfail citing the Q-id. When you fix "
    "the finding remove the marker and the matching entry in tests/architecture/allowlists/invariants.toml "
    "(Q-013, ADR-0130 section 3)."
)


def scan(path: str, text: str) -> list[Violation]:
    found: list[Violation] = []
    for match in XFAIL.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        body = match.group(1)
        qid = REASON_QID.search(body)
        if "strict=True" not in body:
            found.append(Violation(path, line, "non-strict-xfail", body.strip()[:60]))
        elif qid is None:
            found.append(Violation(path, line, "xfail-without-qid", body.strip()[:60]))
        else:
            found.append(Violation(path, line, qid.group(1), "open finding"))
    return found


def collect() -> list[Violation]:
    found: list[Violation] = []
    for path in sorted(INVARIANTS.glob("test_*.py")):
        found += scan(path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8"))
    return found


def meta(v: Violation) -> tuple[str, str, str, str]:
    return "entry", v.rule, "", ""


def test_invariant_xfails_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_every_invariant_xfail_is_strict_and_cites_a_finding() -> None:
    bad = [v for v in collect() if v.rule in {"non-strict-xfail", "xfail-without-qid"}]
    assert not bad, f"{TEACH}\n{bad}"


def test_registry_detects_loose_xfails() -> None:
    text = '@pytest.mark.xfail(reason="Q-001 x")\ndef a(): ...\n@pytest.mark.xfail(strict=True, reason="later")\ndef b(): ...\n'
    assert [v.rule for v in scan("f.py", text)] == ["non-strict-xfail", "xfail-without-qid"]
