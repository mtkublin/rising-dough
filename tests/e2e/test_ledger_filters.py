"""E2E: ledger filters survive refetch, search and pagination (T-D152)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e import db_probe
from tests.ui_map import ledger
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_PAGE_SIZE = 50
_ROWS_A = _PAGE_SIZE + 1
_ROWS_B = 3


def _post_txn(
    page: Page, base_url: str, *, day: str, cat: str, acct: str, amount: str, desc: str
) -> None:
    resp = page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": day,
            "category_id": cat,
            "account_id": acct,
            "amount": amount,
            "description": desc,
        },
    )
    assert resp.ok, resp.text()


def _seed_base(base_url: str, db_path: Path, page: Page) -> tuple[str, str, str]:
    """Create an account and two categories; return (account, alpha, beta) ids."""
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    for name in ("Alpha", "Beta"):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": "expense"}
        ).ok
    return (
        str(db_probe.account_id(db_path, "Checking")),
        str(db_probe.category_id(db_path, "Alpha")),
        str(db_probe.category_id(db_path, "Beta")),
    )


def _seed(base_url: str, db_path: Path, page: Page) -> tuple[str, str]:
    """Seed Alpha/Beta transactions; return (alpha_id, beta_id)."""
    acct, alpha, beta = _seed_base(base_url, db_path, page)
    ids = {"Alpha": alpha, "Beta": beta}
    for i in range(_ROWS_A):
        _post_txn(
            page, base_url, day="2026-01-15", cat=ids["Alpha"], acct=acct,
            amount="1.00", desc=f"alpha apple {i}",
        )  # fmt: skip
    for i in range(_ROWS_B):
        _post_txn(
            page, base_url, day="2026-01-16", cat=ids["Beta"], acct=acct,
            amount="2.00", desc=f"beta banana {i}",
        )  # fmt: skip
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM transactions") == _ROWS_A + _ROWS_B
    return ids["Alpha"], ids["Beta"]


def _rows(page: Page, view: str) -> Locator:
    """One entry per data row of a ledger view (its row-actions kebab)."""
    result: Locator = to_playwright(page, ledger.view_row_actions(view))
    return result


def _open_filtered(live_server: tuple[str, Path], page: Page, *, use_alpha: bool) -> list[str]:
    base_url, db_path = live_server
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    alpha, beta = _seed(base_url, db_path, page)
    page.goto(f"{base_url}/ledger")
    # The unfiltered first page also has _PAGE_SIZE rows, so wait for the filtered
    # response (not just a matching count) before the caller interacts further.
    with page.expect_response(lambda r: "/ledger/table" in r.url and "category" in r.url):
        to_playwright(page, ledger.filter_category).select_option(alpha if use_alpha else beta)
    expect(_rows(page, "actual")).to_have_count(_PAGE_SIZE if use_alpha else _ROWS_B)
    expect(to_playwright(page, ledger.view_table("actual"))).not_to_contain_text(
        "beta banana" if use_alpha else "alpha apple"
    )
    return messages


def _assert_no_include_warning(messages: list[str]) -> None:
    bad = [m for m in messages if "hx-include" in m and "no matches" in m]
    assert not bad, bad


def test_filter_survives_ledger_stale_refetch(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=False)
    page.wait_for_load_state("networkidle")
    with page.expect_response(lambda r: "/ledger/table" in r.url):
        page.evaluate("htmx.trigger(document.body, 'ledger-stale')")
    expect(_rows(page, "actual")).to_have_count(_ROWS_B)
    _assert_no_include_warning(messages)


def test_search_keeps_other_filters(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=False)
    with page.expect_response(lambda r: "q=a" in r.url):
        to_playwright(page, ledger.filter_search).fill("a")
    # "a" matches alpha and beta rows alike; the category filter must still apply.
    expect(_rows(page, "actual")).to_have_count(_ROWS_B)
    with page.expect_response(lambda r: "q=banana" in r.url):
        to_playwright(page, ledger.filter_search).fill("banana")
    expect(_rows(page, "actual")).to_have_count(_ROWS_B)
    _assert_no_include_warning(messages)


def test_pagination_keeps_filters(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=True)
    to_playwright(page, ledger.older_button).click()
    expect(_rows(page, "actual")).to_have_count(_ROWS_A - _PAGE_SIZE)
    expect(to_playwright(page, ledger.view_table("actual"))).not_to_contain_text("beta banana")
    _assert_no_include_warning(messages)


_VIEW_EXTRA = {
    "planned": "&date_from=2026-02-01&date_to=2026-02-28",
    "recurring": "",
}


def _seed_planned_and_recurring(base_url: str, db_path: Path, page: Page) -> str:
    """Seed one planned entry and one rule per category; return Beta's id."""
    acct, alpha, beta = _seed_base(base_url, db_path, page)
    for cat, word in ((alpha, "alpha apple"), (beta, "beta banana")):
        assert page.request.post(
            f"{base_url}/planned",
            form={
                "operation_date": "2026-02-10",
                "category_id": cat,
                "account_id": acct,
                "amount": "5.00",
                "description": word,
            },
        ).ok
        assert page.request.post(
            f"{base_url}/recurring",
            form={
                "cadence": "monthly",
                "start_date": "2026-01-15",
                "category_id": cat,
                "account_id": acct,
                "default_amount": "9.00",
                "default_description": word,
            },
        ).ok
    return beta


@pytest.mark.parametrize("view", ["planned", "recurring"])
def test_other_views_keep_filter_on_refetch_and_search(
    live_server: tuple[str, Path], page: Page, view: str
) -> None:
    base_url, db_path = live_server
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    beta = _seed_planned_and_recurring(base_url, db_path, page)
    page.goto(f"{base_url}/ledger?view={view}{_VIEW_EXTRA[view]}")
    rows = _rows(page, view)
    expect(rows).to_have_count(2)
    to_playwright(page, ledger.filter_category).select_option(beta)
    expect(rows).to_have_count(1)
    page.wait_for_load_state("networkidle")
    with page.expect_response(lambda r: "/ledger/table" in r.url):
        page.evaluate("htmx.trigger(document.body, 'ledger-stale')")
    expect(rows).to_have_count(1)
    expect(to_playwright(page, ledger.table_container)).to_contain_text("banana")
    with page.expect_response(lambda r: "q=a" in r.url):
        to_playwright(page, ledger.filter_search).fill("a")
    expect(rows).to_have_count(1)
    expect(to_playwright(page, ledger.table_container)).not_to_contain_text("apple")
    _assert_no_include_warning(messages)
