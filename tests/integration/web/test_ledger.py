"""T-064 ledger router — unified table + segmented control + fragment aliases."""

from __future__ import annotations

from datetime import date

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)

USER_ID = 1

_SEG_COUNT = 3


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat_exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 1),
                category_id=cat_exp.id,
                account_id=acc.id,
                amount=1234,
                description="Milk",
            ),
        )
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 20),
                category_id=cat_exp.id,
                account_id=acc.id,
                amount=5000,
                description="Rent",
            ),
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=cat_exp.id,
                account_id=acc.id,
                default_amount=50000,
                default_description="Monthly rent",
            ),
        )
        return {
            "acc": acc.id,
            "cat": cat_exp.id,
            "txn": txn.id,
            "pl": pl.id,
            "rule": rule.id,
        }
    finally:
        conn.close()


def test_ledger_index_renders(client: TestClient, seeded: dict[str, int]) -> None:
    """Rising Dough v2 renders the segmented tabs via the shared rd-segmented macro
    (anchor-based full-page nav). The view keys appear in the href query string."""
    r = client.get("/ledger")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    seg = soup.select_one(".rd-segmented")
    assert seg is not None and isinstance(seg, Tag)
    items = seg.select("a.rd-segmented__item")
    assert len(items) == _SEG_COUNT
    hrefs = [a.get("href") for a in items]
    assert hrefs == ["/ledger?view=actual", "/ledger?view=planned", "/ledger?view=recurring"]
    actual_a = items[0]
    assert actual_a.get("aria-selected") == "true"


def test_ledger_view_actual(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=actual")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("[data-ledger-table]")
    assert container is not None and isinstance(container, Tag)
    assert container.get("data-view") == "actual"
    assert soup.find(id=f"txn-{seeded['txn']}") is not None


def test_ledger_view_planned(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=planned")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("[data-ledger-table]")
    assert container is not None and isinstance(container, Tag)
    assert container.get("data-view") == "planned"
    # Status column header present (manual-audit #25 renamed Promoted? → Status).
    headers = {th.get_text(strip=True) for th in soup.select("table.ledger thead th")}
    assert "Status" in headers
    # Promote button targets the modal root.
    btn = soup.find("button", string=lambda s: s is not None and "Promote" in s)
    assert btn is not None and isinstance(btn, Tag)
    assert btn.get("hx-target") == "#modal-root"


def test_ledger_view_recurring(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=recurring")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("[data-ledger-table]")
    assert container is not None and isinstance(container, Tag)
    assert container.get("data-view") == "recurring"
    headers = {th.get_text(strip=True) for th in soup.select("table.ledger thead th")}
    # Manual-audit #25 — Cadence folded into group header, Next due stays.
    assert "Next due" in headers
    assert "Overrides" in headers
    # V.33 — expand reveal is now a sibling <tr>, not a <details>; the
    # Overrides column still surfaces the per-rule override count.
    assert "override" in r.text.lower()


def test_ledger_recurring_lists_each_override_with_remove_button(
    _migrated: Settings,
    client: TestClient,
    seeded: dict[str, int],
) -> None:
    """Every live override on a rule gets a Remove button targeting its own
    canonical ``occurrence_date`` delete endpoint. Covers the multi-future-
    override case where only the override on ``next_due`` was previously
    reachable via UI."""
    client.post(
        f"/recurring/{seeded['rule']}/overrides",
        data={"year": 2026, "month": 2, "amount": "100.00"},
    )
    client.post(
        f"/recurring/{seeded['rule']}/overrides",
        data={"year": 2026, "month": 3, "amount": "200.00"},
    )
    r = client.get("/ledger?view=recurring")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    # V.33 — expand reveal is a sibling <tr>; Remove buttons live inside
    # .rd-rec-over-item rows now.
    remove_btns = soup.select(".rd-rec-over-item button")
    assert len(remove_btns) >= 2
    endpoints = {btn.get("hx-post") for btn in remove_btns}
    assert f"/recurring/{seeded['rule']}/overrides/2026-02-01/delete" in endpoints
    assert f"/recurring/{seeded['rule']}/overrides/2026-03-01/delete" in endpoints

    # Clicking Remove on the second override calls the delete endpoint and
    # the row re-rendered via the ledger-stale trigger drops that override.
    resp = client.post(f"/recurring/{seeded['rule']}/overrides/2026-03-01/delete")
    assert resp.status_code == 200
    conn = get_connection(_migrated)
    try:
        remaining = recurring_repo.list_overrides(conn, USER_ID, seeded["rule"])
    finally:
        conn.close()
    assert [ov.occurrence_date for ov in remaining] == [date(2026, 2, 1)]


def test_ledger_invalid_view_falls_back_to_actual(
    client: TestClient, seeded: dict[str, int]
) -> None:
    r = client.get("/ledger?view=nonsense")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("[data-ledger-table]")
    assert container is not None and isinstance(container, Tag)
    assert container.get("data-view") == "actual"


def test_ledger_fragment_is_not_full_page(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger/table?view=actual")
    assert r.status_code == 200
    assert "<html" not in r.text


def test_ledger_fragment_alias_transactions(client: TestClient, seeded: dict[str, int]) -> None:
    """Legacy /transactions/table alias returns a structurally-equivalent
    fragment to /ledger/table?view=actual."""
    r_legacy = client.get("/transactions/table")
    r_new = client.get("/ledger/table?view=actual")
    assert r_legacy.status_code == 200
    assert r_new.status_code == 200
    legacy_soup = BeautifulSoup(r_legacy.text, "html.parser")
    new_soup = BeautifulSoup(r_new.text, "html.parser")
    legacy_container = legacy_soup.select_one("[data-ledger-table]")
    new_container = new_soup.select_one("[data-ledger-table]")
    assert legacy_container is not None and isinstance(legacy_container, Tag)
    assert new_container is not None and isinstance(new_container, Tag)
    assert legacy_container.get("data-view") == new_container.get("data-view") == "actual"
    legacy_headers = [th.get_text(strip=True) for th in legacy_soup.select("table.ledger thead th")]
    new_headers = [th.get_text(strip=True) for th in new_soup.select("table.ledger thead th")]
    assert legacy_headers == new_headers


def test_ledger_fragment_alias_planned(client: TestClient, seeded: dict[str, int]) -> None:
    """Legacy /planned/table alias delegates to view=planned."""
    r_legacy = client.get("/planned/table")
    r_new = client.get("/ledger/table?view=planned")
    assert r_legacy.status_code == 200
    assert r_new.status_code == 200
    legacy_soup = BeautifulSoup(r_legacy.text, "html.parser")
    new_soup = BeautifulSoup(r_new.text, "html.parser")
    legacy_container = legacy_soup.select_one("[data-ledger-table]")
    new_container = new_soup.select_one("[data-ledger-table]")
    assert legacy_container is not None and isinstance(legacy_container, Tag)
    assert new_container is not None and isinstance(new_container, Tag)
    assert legacy_container.get("data-view") == new_container.get("data-view") == "planned"
    legacy_headers = [th.get_text(strip=True) for th in legacy_soup.select("table.ledger thead th")]
    new_headers = [th.get_text(strip=True) for th in new_soup.select("table.ledger thead th")]
    assert legacy_headers == new_headers


def test_ledger_filter_by_category(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        salary = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 2),
                category_id=salary.id,
                account_id=seeded["acc"],
                amount=1_000_000,
                description="Payday",
            ),
        )
    finally:
        conn.close()
    r = client.get(f"/ledger/table?view=actual&category_id={seeded['cat']}")
    assert r.status_code == 200
    assert "Milk" in r.text
    assert "Payday" not in r.text


def test_ledger_planned_excludes_virtual_rows(client: TestClient, seeded: dict[str, int]) -> None:
    """T-119 regression pin: Planned tab must NOT surface virtual
    occurrences expanded from the active recurring rule. The seeded fixture
    already includes an active monthly rule — none of its occurrences
    should appear in the Planned view."""
    r = client.get("/ledger?view=planned")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    # Only the one persisted planned row should render.
    rows = soup.select("#planned-table tbody tr.row")
    assert len(rows) == 1
    row = rows[0]
    row_id = row.get("id")
    assert isinstance(row_id, str)
    assert row_id.startswith("planned-p-"), f"got id={row_id!r}"
    # "Monthly rent" is the recurring rule's default_description — it must not
    # leak into the Planned view (it belongs under /ledger?view=recurring).
    assert "Monthly rent" not in r.text


def test_ledger_table_wrapper_exposes_segmented_swap_target(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """T-092: segmented control targets ``#ledger-table`` with ``outerHTML``
    swap. Both the page and the fragment response must contain the wrapper so
    the swap resolves and the inner view id is preserved for legacy selectors.
    """
    for view, inner_id in (
        ("actual", "txn-table"),
        ("planned", "planned-table"),
        ("recurring", "recurring-table"),
    ):
        r = client.get(f"/ledger/table?view={view}")
        assert r.status_code == 200, view
        soup = BeautifulSoup(r.text, "html.parser")
        wrapper = soup.find(id="ledger-table")
        assert wrapper is not None and isinstance(wrapper, Tag), view
        inner = soup.find(id=inner_id)
        assert inner is not None and isinstance(inner, Tag), view


def test_ledger_actual_rows_sorted_desc_by_date(client: TestClient, _migrated: Settings) -> None:
    """Ledger Actual tab sorts transactions by operation_date DESC (newest
    first), with id DESC as tie-break. Pinned so pagination plus sort order
    stay user-expected after schema or repo refactors."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        for day, desc in ((1, "oldest"), (15, "middle"), (28, "newest")):
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=date(2026, 10, day),
                    category_id=cat.id,
                    account_id=acc.id,
                    amount=1000,
                    description=desc,
                ),
            )
    finally:
        conn.close()

    r = client.get("/ledger/table?view=actual")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("#txn-table tbody tr.row")
    descriptions = [row.get_text(strip=False) for row in rows]
    newest_idx = next(i for i, t in enumerate(descriptions) if "newest" in t)
    middle_idx = next(i for i, t in enumerate(descriptions) if "middle" in t)
    oldest_idx = next(i for i, t in enumerate(descriptions) if "oldest" in t)
    assert newest_idx < middle_idx < oldest_idx, (
        f"expected DESC by date; got newest@{newest_idx} middle@{middle_idx} oldest@{oldest_idx}"
    )
