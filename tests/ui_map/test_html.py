"""Resolver tests: UI-map locators evaluated over small HTML fixtures."""

from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from tests.ui_map import _html, shell
from tests.ui_map.locator import Locator, by_id, by_testid, label, role, to_playwright

PAGE = """
<nav aria-label="Primary navigation"><ul>
  <li><a href="/today" aria-current="page"><span>Today</span><span>g o</span></a></li>
  <li><a href="/ledger">Ledger</a></li>
</ul></nav>
<main id="main">
  <h1>Ledger</h1><h2>Filters</h2>
  <form>
    <label for="q">Search</label><input id="q" name="q">
    <label>Amount <input type="text" name="amount"></label>
    <input type="checkbox" id="c1"><label for="c1">Include planned</label>
    <select aria-label="Account"><option>Cash</option></select>
    <input type="text" aria-labelledby="pwl"><span id="pwl">Secret word</span>
    <button type="submit">Save</button>
    <button type="button" aria-label="Close dialog">x</button>
    <button hidden>Hidden save</button>
  </form>
  <table id="txn-table">
    <tr id="txn-7"><td>Coffee</td><td><button aria-label="Row actions">...</button></td></tr>
    <tr id="txn-8"><td>Tea</td><td><button aria-label="Row actions">...</button></td></tr>
  </table>
  <dialog open aria-label="Edit"><p>hi</p></dialog>
  <div data-testid="odd"></div>
</main>
"""


def test_role_with_name_substring_case_insensitive() -> None:
    link = _html.resolve_one(PAGE, role("link", "today"))
    assert link["href"] == "/today"


def test_role_exact_name_requires_full_match() -> None:
    assert _html.exists(PAGE, role("link", "Today g o", exact=True))
    assert not _html.exists(PAGE, role("link", "Today", exact=True))


def test_role_name_regex() -> None:
    assert _html.count(PAGE, role("link", re.compile(r"^L"))) == 1


def test_heading_level() -> None:
    assert _html.text_of(PAGE, role("heading", level=1)) == "Ledger"
    assert _html.text_of(PAGE, role("heading", level=2)) == "Filters"


def test_textbox_checkbox_combobox_and_dialog_roles() -> None:
    assert _html.count(PAGE, role("textbox")) == 3  # q, amount, secret
    assert _html.exists(PAGE, role("checkbox", "Include planned"))
    assert _html.exists(PAGE, role("combobox", "Account"))
    assert _html.exists(PAGE, role("dialog", "Edit"))


def test_row_and_cell_roles() -> None:
    assert _html.count(PAGE, role("row")) == 2
    assert _html.count(PAGE, role("cell")) == 4


def test_accessible_name_sources() -> None:
    assert _html.exists(PAGE, role("button", "Save"))
    assert _html.exists(PAGE, role("button", "Close dialog"))
    assert _html.exists(PAGE, role("textbox", "Secret word"))
    assert _html.exists(PAGE, role("textbox", "Search"))


def test_hidden_elements_excluded_from_role_queries() -> None:
    assert not _html.exists(PAGE, role("button", "Hidden save"))


def test_label_for_wrapping_and_aria_label() -> None:
    assert _html.resolve_one(PAGE, label("Search"))["id"] == "q"
    assert _html.resolve_one(PAGE, label("Amount"))["name"] == "amount"
    assert _html.resolve_one(PAGE, label("Account")).name == "select"


def test_label_exact() -> None:
    assert not _html.exists(PAGE, label("Sear", exact=True))
    assert _html.exists(PAGE, label("Search", exact=True))


def test_id_and_prefix() -> None:
    assert _html.exists(PAGE, by_id("txn-table"))
    assert _html.count(PAGE, by_id("txn-", prefix=True)) == 3  # txn-table, txn-7, txn-8


def test_by_testid() -> None:
    assert _html.exists(PAGE, by_testid("odd"))


def test_within_scopes_the_query() -> None:
    row7 = by_id("txn-7")
    menu = role("button", "Row actions").inside(row7)
    assert _html.count(PAGE, menu) == 1
    assert _html.count(PAGE, role("button", "Row actions")) == 2


def test_shell_nav_link_resolves() -> None:
    assert _html.exists(PAGE, shell.nav_link("Ledger"))
    assert not _html.exists(PAGE, shell.nav_link("Nope"))


def test_resolve_one_raises_on_ambiguity_or_absence() -> None:
    with pytest.raises(LookupError):
        _html.resolve_one(PAGE, role("row"))
    with pytest.raises(LookupError):
        _html.resolve_one(PAGE, role("heading", "Missing"))


def test_accepts_prebuilt_soup() -> None:
    soup = BeautifulSoup(PAGE, "html.parser")
    assert _html.exists(soup, by_id("main"))


class _Recorder:
    """Duck-typed Playwright page recording the calls it receives."""

    def __init__(self, calls: list[tuple[str, tuple[object, ...], dict[str, object]]]) -> None:
        self.calls = calls

    def _rec(self, _method: str, *a: object, **k: object) -> _Recorder:
        self.calls.append((_method, a, k))
        return self

    def get_by_role(self, *a: object, **k: object) -> _Recorder:
        return self._rec("get_by_role", *a, **k)

    def get_by_label(self, *a: object, **k: object) -> _Recorder:
        return self._rec("get_by_label", *a, **k)

    def get_by_test_id(self, *a: object, **k: object) -> _Recorder:
        return self._rec("get_by_test_id", *a, **k)

    def locator(self, *a: object, **k: object) -> _Recorder:
        return self._rec("locator", *a, **k)


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        (
            role("heading", "Ledger", level=1),
            [("get_by_role", ("heading",), {"exact": False, "name": "Ledger", "level": 1})],
        ),
        (label("Email"), [("get_by_label", ("Email",), {"exact": False})]),
        (by_id("txn-7"), [("locator", ('[id="txn-7"]',), {})]),
        (by_id("txn-", prefix=True), [("locator", ('[id^="txn-"]',), {})]),
        (by_testid("odd"), [("get_by_test_id", ("odd",), {})]),
    ],
)
def test_to_playwright_maps_each_kind(loc: Locator, expected: list[object]) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    to_playwright(_Recorder(calls), loc)
    assert calls == expected


def test_to_playwright_chains_within_scope_first() -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    to_playwright(_Recorder(calls), role("button", "Row actions").inside(by_id("txn-7")))
    assert [c[0] for c in calls] == ["locator", "get_by_role"]
