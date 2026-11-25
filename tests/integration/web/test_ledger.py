"""T-064 ledger router — unified table + segmented control + fragment aliases."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
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
from tests.ui_map import _html, ledger
from tests.ui_map.locator import by_id

USER_ID = 1

_VIEW_TABS = ("actual", "planned", "recurring")
_MINUS = "\N{MINUS SIGN}"


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
                operation_date=clock.today_local(Settings()) + timedelta(days=10),
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
    """The view tabs are links carrying the counts; the open one is aria-current."""
    r = client.get("/ledger")
    assert r.status_code == 200
    items = [_html.resolve_one(r.text, ledger.view_tab(n)) for n in _VIEW_TABS]
    assert [a.get_text(strip=True) for a in items] == ["actual 1", "planned 1", "recurring 1"]
    assert [a.get("href") for a in items] == [
        "/ledger",
        "/ledger?view=planned",
        "/ledger?view=recurring",
    ]
    assert [a.get("aria-current") for a in items] == ["page", None, None]


def test_ledger_view_actual(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=actual")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ledger.view_table("actual")).get("data-view") == "actual"
    assert _html.exists(r.text, ledger.row(seeded["txn"]))


def test_ledger_view_planned(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=planned")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ledger.view_table("planned")).get("data-view") == "planned"
    # Status column header present (manual-audit #25 renamed Promoted? → Status).
    assert _html.exists(r.text, ledger.column_header("Status"))
    # Promote button targets the modal root.
    btn = _html.resolve(r.text, ledger.promote)[0]
    assert btn.get("hx-target") == "#modal-root"


def test_ledger_view_recurring(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger?view=recurring")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ledger.view_table("recurring")).get("data-view") == "recurring"
    # Manual-audit #25 — Cadence folded into group header, Next due stays.
    assert _html.exists(r.text, ledger.column_header("Next due"))
    # V.33 — the Overrides column still surfaces the per-rule override count.
    assert _html.exists(r.text, ledger.column_header("Overrides"))


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
    # V.33 — the expand reveal is a (collapsed) sibling row holding the Remove
    # buttons; it is hidden until toggled, so navigate from its mapped row.
    expand = _html.resolve_one(r.text, ledger.recurring_expand(seeded["rule"]))
    remove_btns = expand.find_all("button", string="Remove")
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


def test_ledger_invalid_view_is_422_and_empty_view_is_actual(
    client: TestClient, seeded: dict[str, int]
) -> None:
    assert client.get("/ledger?view=nonsense").status_code == 422
    r = client.get("/ledger?view=")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ledger.view_table("actual")).get("data-view") == "actual"


def test_ledger_fragment_is_not_full_page(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/ledger/table?view=actual")
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.table_container)
    assert not _html.exists(r.text, ledger.heading)  # no page chrome


def _headers(html: str) -> list[str]:
    return [" ".join(th.get_text(" ").split()) for th in _html.resolve(html, ledger.any_header)]


def _assert_same_fragment(legacy: str, new: str, view: str) -> None:
    for html in (legacy, new):
        assert _html.resolve_one(html, ledger.view_table(view)).get("data-view") == view
    assert _headers(legacy) == _headers(new)


def test_ledger_fragment_alias_transactions(client: TestClient, seeded: dict[str, int]) -> None:
    """Legacy /transactions/table alias returns a structurally-equivalent
    fragment to /ledger/table?view=actual."""
    r_legacy = client.get("/transactions/table")
    r_new = client.get("/ledger/table?view=actual")
    assert r_legacy.status_code == 200
    assert r_new.status_code == 200
    _assert_same_fragment(r_legacy.text, r_new.text, "actual")


def test_ledger_fragment_alias_planned(client: TestClient, seeded: dict[str, int]) -> None:
    """Legacy /planned/table alias delegates to view=planned."""
    r_legacy = client.get("/planned/table")
    r_new = client.get("/ledger/table?view=planned")
    assert r_legacy.status_code == 200
    assert r_new.status_code == 200
    _assert_same_fragment(r_legacy.text, r_new.text, "planned")


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
    texts = _row_texts(r.text, "actual")
    assert any("Milk" in t for t in texts)
    assert not any("Payday" in t for t in texts)


def test_ledger_planned_excludes_virtual_rows(client: TestClient, seeded: dict[str, int]) -> None:
    """T-119 regression pin: Planned tab must NOT surface virtual
    occurrences expanded from the active recurring rule. The seeded fixture
    already includes an active monthly rule — none of its occurrences
    should appear in the Planned view."""
    r = client.get("/ledger?view=planned")
    assert r.status_code == 200
    # Only the one persisted planned row should render.
    rows = [t for t in _html.resolve(r.text, ledger.any_planned_row) if t.name == "tr"]
    assert [row.get("id") for row in rows] == [f"planned-p-{seeded['pl']}"]
    # "Monthly rent" is the recurring rule's default_description — it must not
    # leak into the Planned view (it belongs under /ledger?view=recurring).
    assert not any("Monthly rent" in t for t in _row_texts(r.text, "planned"))


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
        assert _html.exists(r.text, ledger.table_container), view
        assert _html.exists(r.text, by_id(inner_id)), view
        assert _html.exists(r.text, ledger.view_table(view)), view


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
    descriptions = _row_texts(r.text, "actual")
    newest_idx = next(i for i, t in enumerate(descriptions) if "newest" in t)
    middle_idx = next(i for i, t in enumerate(descriptions) if "middle" in t)
    oldest_idx = next(i for i, t in enumerate(descriptions) if "oldest" in t)
    assert newest_idx < middle_idx < oldest_idx, (
        f"expected DESC by date; got newest@{newest_idx} middle@{middle_idx} oldest@{oldest_idx}"
    )


def _row_texts(html: str, view: str) -> list[str]:
    """Visible text of each data row (row ids mark data rows; group heads have none)."""
    return [
        " ".join(row.get_text(" ").split())
        for row in _html.resolve(html, ledger.table_rows(view))
        if row.get("id")
    ]


def _day_net_text(html: str, day_label: str) -> str:
    """The net figure in a day-group header (``""`` when the header omits it)."""
    head = _html.text_of(html, ledger.day_head(day_label))
    return head.split(day_label, 1)[1].strip()


def test_actual_day_net_with_negative_reconciliation(
    client: TestClient, _migrated: Settings
) -> None:
    """T-D48 — -700 reconciliation + -100 + -50 expenses nets -850.00, not positive."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        rec = categories_repo.find_by_name(conn, USER_ID, "Reconciliation")
        assert rec is not None
        day = date(2026, 11, 2)
        for cat_id, amount in ((rec.id, -70000), (exp.id, 10000), (exp.id, 5000)):
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=day,
                    category_id=cat_id,
                    account_id=acc.id,
                    amount=amount,
                    description="x",
                ),
            )
    finally:
        conn.close()
    r = client.get("/ledger?view=actual")
    assert r.status_code == 200
    assert _day_net_text(r.text, "MON 02 NOV") == f"NET {_MINUS}850.00"


def _seed_eur_day(settings: Settings, *, with_rate: bool) -> None:
    from decimal import Decimal  # noqa: PLC0415

    from budget_planner.domain.fx import NewFxRate  # noqa: PLC0415
    from budget_planner.repositories import fx as fx_repo  # noqa: PLC0415

    conn = get_connection(settings)
    try:
        eur = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Euro", currency="EUR", opening_balance=0)
        )
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        rec = categories_repo.find_by_name(conn, USER_ID, "Reconciliation")
        assert rec is not None
        day = date(2026, 11, 2)
        if with_rate:
            fx_repo.upsert_rate(
                conn, NewFxRate(date=day, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4"))
            )
        for cat_id, amount in ((rec.id, -10000), (exp.id, 2500)):
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=day,
                    category_id=cat_id,
                    account_id=eur.id,
                    amount=amount,
                    description="x",
                ),
            )
    finally:
        conn.close()


def test_actual_day_net_converts_foreign_currency_to_base(
    client: TestClient, _migrated: Settings
) -> None:
    """T-D48 — EUR -100 reconciliation, -25 expense at 4.0 -> net -500.00 PLN."""
    _seed_eur_day(_migrated, with_rate=True)
    r = client.get("/ledger?view=actual")
    assert _day_net_text(r.text, "MON 02 NOV") == f"NET {_MINUS}500.00"


def test_actual_render_never_fetches_fx_and_hides_net_on_cache_miss(
    client: TestClient, _migrated: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rendering /ledger must not touch the network; uncached day hides its net."""
    import httpx  # noqa: PLC0415

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("network FX fetch during ledger render")

    monkeypatch.setattr(httpx.Client, "get", _boom)
    monkeypatch.setattr(httpx.Client, "send", _boom)
    _seed_eur_day(_migrated, with_rate=False)
    r = client.get("/ledger?view=actual")
    assert r.status_code == 200
    assert _day_net_text(r.text, "MON 02 NOV") == ""
