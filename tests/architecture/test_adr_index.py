# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G14: ADR index guard (Q-051; ADR-0130 section 10).

Rules (one violation per finding, keyed by the offending file):

* ``duplicate-number``: two ADR files share a number (0105 and 0121 are grandfathered, not renumbered);
* ``number-gap``: a number is missing from the sequence (0044 is grandfathered);
* ``not-in-index``: an ADR file has no row in ``docs/adr/README.md``;
* ``dead-link``: an index link does not resolve to a file;
* ``index-unsorted``: index rows are not in ascending number order;
* ``no-status``: the ADR has no ``Status`` line.

Allowlist: ``allowlists/adr_index.toml``.
"""

from __future__ import annotations

import re
from collections import Counter

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "adr_index"
HEADER = "G14 adr_index: grandfathered ADR index irregularities (duplicate 0105/0121, gap 0044) and open docs debt (Q-051)."
ADR_DIR = REPO_ROOT / "docs" / "adr"
FILE = re.compile(r"^(\d{4})-.+\.md$")
ROW = re.compile(r"^\|\s*(\d{4})\s*\|.*?\(([^)]+\.md)\)")
STATUS = re.compile(r"^-?\s*\**Status\**\s*:", re.I | re.M)
TEACH = (
    "G14 ADR index: every ADR needs a unique number, a Status line and a row in docs/adr/README.md with a working "
    "link, in ascending order. 0105 and 0121 are grandfathered duplicates (ADR-0130 section 10; Q-051)."
)


def scan(files: dict[str, str], readme: str) -> list[Violation]:
    """``files``: ADR file name -> text. ``readme``: text of the index."""
    rel = "docs/adr/"
    found: list[Violation] = []
    numbers = Counter(m.group(1) for name in files if (m := FILE.match(name)))
    for number, n in sorted(numbers.items()):
        if n > 1:
            found.append(Violation(f"{rel}{number}", 0, "duplicate-number", f"{n} files"))
    present = sorted(int(n) for n in numbers)
    for missing in sorted(set(range(1, present[-1] + 1)) - set(present)) if present else []:
        found.append(Violation(f"{rel}{missing:04d}", 0, "number-gap", "missing number"))
    rows = [(m.group(1), m.group(2)) for line in readme.splitlines() if (m := ROW.match(line))]
    indexed = {link for _n, link in rows}
    for name, text in sorted(files.items()):
        if not FILE.match(name):
            continue
        if name not in indexed:
            found.append(Violation(rel + name, 0, "not-in-index", name))
        if not STATUS.search(text):
            found.append(Violation(rel + name, 0, "no-status", name))
    for _n, link in rows:
        if link not in files:
            found.append(Violation(f"{rel}README.md", 0, "dead-link", link))
    order = [n for n, _l in rows]
    if order != sorted(order):
        found.append(Violation(f"{rel}README.md", 0, "index-unsorted", "rows not ascending"))
    return found


def collect() -> list[Violation]:
    files = {
        p.name: p.read_text(encoding="utf-8") for p in ADR_DIR.glob("*.md") if p.name != "README.md"
    }
    return scan(files, (ADR_DIR / "README.md").read_text(encoding="utf-8"))


def meta(v: Violation) -> tuple[str, str, str, str]:
    if v.rule in {"duplicate-number", "number-gap"}:
        return (
            "permanent",
            "Q-051",
            "",
            "grandfathered (ADR-0130 section 10): not renumbered to keep references stable",
        )
    return "entry", "Q-051", "E14", ""


def test_adr_index_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_adr_index_detects_fixture_violations() -> None:
    files = {
        "0001-a.md": "- **Status**: Accepted\n",
        "0001-b.md": "no status\n",
        "0003-c.md": "Status: x\n",
    }
    readme = "| 0003 | [C](0003-c.md) |\n| 0001 | [A](0001-a.md) |\n| 0002 | [X](0002-x.md) |\n"
    rules = {v.rule for v in scan(files, readme)}
    assert rules == {
        "duplicate-number",
        "number-gap",
        "not-in-index",
        "no-status",
        "dead-link",
        "index-unsorted",
    }
