"""The intended-differences parser and its tie to ``derived.md`` (ADR-0147 amendment)."""

from __future__ import annotations

from tests.visual import handoff, intended
from tests.visual.test_reference import INTENDED

TABLE = """\
intro

## Intended differences

text

| Page | Shards | Decision | Reason | Operator sign-off |
|---|---|---|---|---|
| a, b/c | 1440 and 1024, light and dark | D1 | why one | op |
| d | all | D2 | why two | op |
| overlays/e | focus ring after the 422 | x | why three | op |
| f | 1024 dark | D4 | why four | op |

## Next

| z | all | D9 | no | op |
"""


def test_parse_expands_pages_widths_and_themes() -> None:
    got = intended.parse(TABLE)
    assert got[("pages/a.html", "1440", "light")] == "D1: why one"
    assert got[("pages/b/c.html", "1024", "dark")] == "D1: why one"
    assert ("pages/a.html", "375", "light") not in got
    assert {k for k in got if k[0] == "pages/d.html"} == {
        ("pages/d.html", w, t) for w in ("1440", "1024", "375") for t in ("light", "dark")
    }
    assert len([k for k in got if k[0] == "pages/overlays/e.html"]) == 6
    assert [k for k in got if k[0] == "pages/f.html"] == [("pages/f.html", "1024", "dark")]
    assert not any(k[0] == "pages/z.html" for k in got)


def test_parse_without_section_is_empty() -> None:
    assert intended.parse("# nothing\n") == {}


def test_derived_table_is_the_marked_set() -> None:
    known = frozenset(handoff.pages())
    table = intended.load(known)
    assert table, "derived.md lists intended differences"
    assert table == INTENDED
    assert {page for page, _, _ in table} <= known
    accounts = [k for k in table if k[0] == "pages/accounts.html"]
    assert len(accounts) == 4
    assert all(w != "375" for _, w, _ in accounts)


def test_bare_overlay_name_resolves_under_overlays() -> None:
    known = frozenset({"pages/overlays/e.html", "pages/a.html"})
    got = intended.parse(TABLE.replace("overlays/e", "e"), known)
    assert ("pages/overlays/e.html", "1440", "dark") in got
    assert ("pages/a.html", "1440", "dark") in got
