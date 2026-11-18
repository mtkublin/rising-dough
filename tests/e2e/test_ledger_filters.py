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


def _seed(base_url: str, page: Page) -> tuple[str, str]:
    """Create an account, two categories and rows; return (alpha_id, beta_id)."""
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
    page.locator("select[name=category_id]").select_option(alpha if use_alpha else beta)
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_PAGE_SIZE if use_alpha else _ROWS_B)
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
    page.get_by_role("button", name="Older").click()
    expect(page.locator(_ROW_SELECTOR)).to_have_count(_ROWS_A - _PAGE_SIZE)
    expect(page.locator("#txn-table")).not_to_contain_text("beta banana")
    _assert_no_include_warning(messages)
