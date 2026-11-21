"""E2E: ledger filters survive refetch, search and pagination (T-D152)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import strip_id_prefix

pytestmark = pytest.mark.e2e

_PAGE_SIZE = 50
_ROWS_A = _PAGE_SIZE + 1
_ROWS_B = 3
_ROW_SELECTOR = "#txn-table tbody tr[id^='txn-']"


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


def _seed_base(base_url: str, page: Page) -> tuple[str, str, str]:
    """Create an account and two categories; return (account, alpha, beta) ids."""
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    for name in ("Alpha", "Beta"):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": "expense"}
        ).ok
    page.goto(f"{base_url}/accounts")
    acct = strip_id_prefix(page.locator("tr[id^='account-']").first.get_attribute("id"), "account-")
    page.goto(f"{base_url}/categories")
    ids: dict[str, str] = {}
    for name in ("Alpha", "Beta"):
        row = page.locator("[id^='category-']", has_text=name).first
        ids[name] = strip_id_prefix(row.get_attribute("id"), "category-")
    return acct, ids["Alpha"], ids["Beta"]


def _seed(base_url: str, page: Page) -> tuple[str, str]:
    """Seed Alpha/Beta transactions; return (alpha_id, beta_id)."""
    acct, alpha, beta = _seed_base(base_url, page)
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
    return ids["Alpha"], ids["Beta"]


def _open_filtered(live_server: tuple[str, Path], page: Page, *, use_alpha: bool) -> list[str]:
    base_url, _ = live_server
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    alpha, beta = _seed(base_url, page)
    page.goto(f"{base_url}/ledger")
    page.wait_for_function("typeof window.htmx === 'object'")
    wanted = alpha if use_alpha else beta
    # Await the filtered response itself: with Alpha the unfiltered first page
    # also has 50 rows, so a row count alone cannot tell the two apart (T-Q248).
    with page.expect_response(lambda r: f"category_id={wanted}" in r.url):
        page.locator("select[name=category_id]").select_option(wanted)
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_PAGE_SIZE if use_alpha else _ROWS_B)
    page.wait_for_function("document.querySelector('#ledger-table.htmx-request') === null")
    return messages


def _assert_no_include_warning(messages: list[str]) -> None:
    bad = [m for m in messages if "hx-include" in m and "no matches" in m]
    assert not bad, bad


def test_filter_survives_ledger_stale_refetch(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=False)
    page.wait_for_load_state("networkidle")
    with page.expect_response(lambda r: "/ledger/table" in r.url):
        page.evaluate("htmx.trigger(document.body, 'ledger-stale')")
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_ROWS_B)
    _assert_no_include_warning(messages)


def test_search_keeps_other_filters(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=False)
    with page.expect_response(lambda r: "q=a" in r.url):
        page.locator("input[name=q]").fill("a")
    # "a" matches alpha and beta rows alike; the category filter must still apply.
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_ROWS_B)
    with page.expect_response(lambda r: "q=banana" in r.url):
        page.locator("input[name=q]").fill("banana")
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_ROWS_B)
    _assert_no_include_warning(messages)


def test_pagination_keeps_filters(live_server: tuple[str, Path], page: Page) -> None:
    messages = _open_filtered(live_server, page, use_alpha=True)
    with page.expect_response(lambda r: "page=2" in r.url):
        page.get_by_role("button", name="Older").click()
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_ROWS_A - _PAGE_SIZE)
    expect(page.locator("#txn-table")).not_to_contain_text("beta banana")
    _assert_no_include_warning(messages)


_VIEW_ROWS = {
    "planned": ("tr[id^='planned-p-']", "&date_from=2026-02-01&date_to=2026-02-28"),
    "recurring": ("tr[id^='recurring-']", ""),
}


def _seed_planned_and_recurring(base_url: str, page: Page) -> str:
    """Seed one planned entry and one rule per category; return Beta's id."""
    acct, alpha, beta = _seed_base(base_url, page)
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
    base_url, _ = live_server
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    beta = _seed_planned_and_recurring(base_url, page)
    selector, extra = _VIEW_ROWS[view]
    page.goto(f"{base_url}/ledger?view={view}{extra}")
    rows = page.locator(selector)
    expect(rows).to_have_count(2)
    page.locator("select[name=category_id]").select_option(beta)
    expect(rows).to_have_count(1)
    page.wait_for_load_state("networkidle")
    with page.expect_response(lambda r: "/ledger/table" in r.url):
        page.evaluate("htmx.trigger(document.body, 'ledger-stale')")
    expect(rows).to_have_count(1)
    expect(page.locator("#ledger-table")).to_contain_text("banana")
    with page.expect_response(lambda r: "q=a" in r.url):
        page.locator("input[name=q]").fill("a")
    expect(rows).to_have_count(1)
    expect(page.locator("#ledger-table")).not_to_contain_text("apple")
    _assert_no_include_warning(messages)
