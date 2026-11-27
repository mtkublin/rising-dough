"""Empty-state links open their dialog in place (T-UR52).

A plain ``href`` to a dialog fragment navigates to a page without a shell. Each link
must carry the same ``hx-get`` / ``#modal-root`` attributes as the working header button.
"""

from __future__ import annotations

from bs4 import Tag

from budget_planner.config import Settings
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html, accounts
from tests.ui_map.locator import role


def _render(fragment: str, /, **context: object) -> str:
    return build_jinja_env(Settings(_env_file=None)).get_template(fragment).render(**context)


def _opens_in_modal(link: Tag, url: str) -> None:
    attrs = link.attrs
    assert (attrs["href"], attrs["hx-get"], attrs["hx-target"], attrs["hx-swap"]) == (
        url,
        url,
        "#modal-root",
        "innerHTML",
    )


def test_accounts_empty_state_cta_opens_the_dialog() -> None:
    html = _render("fragments/states/accounts-empty.html")
    _opens_in_modal(_html.resolve_one(html, accounts.new_account_cta), "/accounts/new")


def test_recurring_empty_state_cta_opens_the_dialog() -> None:
    html = _render("fragments/states/recurring-empty.html")
    _opens_in_modal(
        _html.resolve_one(html, role("link", "[ new entry ]", exact=True)),
        "/add?when=happened&dialog=1",
    )


def test_ledger_first_run_new_account_opens_the_dialog() -> None:
    html = _render("fragments/states/ledger-first-run.html")
    _opens_in_modal(
        _html.resolve_one(html, role("link", "new account", exact=True)), "/accounts/new"
    )


def test_planned_empty_state_cta_opens_the_dialog() -> None:
    html = _render("fragments/states/planned-empty.html")
    _opens_in_modal(
        _html.resolve_one(html, role("link", "[ new entry ]", exact=True)),
        "/add?when=happened&dialog=1",
    )


def test_ledger_first_run_new_entry_opens_the_dialog() -> None:
    html = _render("fragments/states/ledger-first-run.html")
    _opens_in_modal(
        _html.resolve_one(html, role("link", "[ new entry ]", exact=True)),
        "/add?when=happened&dialog=1",
    )
