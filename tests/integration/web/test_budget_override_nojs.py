"""The override dialog route opened as a plain page (link without HTMX, T-UR84).

A direct load renders the dialog inside the app shell with the stylesheet; over HTMX it stays the
bare fragment aimed at ``#modal-root``; a failed save re-renders the page with the field error.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import budgets as budgets_repo, categories as categories_repo
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import USER_ID, audit_count, audit_total
from tests.ui_map import _html, plan, rd_dialogs, rd_shell
from tests.ui_map.locator import by_id

pytest_plugins = ("tests.contract.test_plan_support",)

HX = {"HX-Request": "true"}


def _url(cat_id: int) -> str:
    return f"/budget/rules/{cat_id}/overrides/new?year=2026&month=10&tier=default"


def test_plain_get_is_a_styled_page_with_the_dialog(client: TestClient, cat_id: int) -> None:
    r = client.get(_url(cat_id))

    assert r.status_code == 200
    assert _html.exists(r.text, rd_shell.nav_desktop)
    assert _html.exists(r.text, rd_shell.modal_root)
    assert _html.count(r.text, plan.override_tier) == 3
    assert _html.exists(r.text, plan.override_save)
    assert _html.exists(r.text, by_id("override-budget-title"))


def test_htmx_get_stays_the_bare_fragment(client: TestClient, cat_id: int) -> None:
    r = client.get(_url(cat_id), headers=HX)

    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert not _html.exists(r.text, rd_shell.nav_desktop)
    assert not _html.exists(r.text, rd_shell.modal_root)
    assert _html.count(r.text, plan.override_tier) == 3


def test_second_users_category_is_404(client: TestClient, db: sqlite3.Connection) -> None:
    seed_login_user(db, user_id=2, email="other@example.com")
    other = categories_repo.create(db, 2, NewCategory(name="Other", direction=Direction.EXPENSE))
    db.commit()

    assert client.get(_url(other.id)).status_code == 404


def test_failed_save_rerenders_the_page_with_the_error(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    r = client.post(
        f"/budget/rules/{cat_id}/overrides",
        data={"tier": "default", "amount": "abc", "year": "2026", "month": "10"},
    )

    assert r.status_code == 422
    assert _html.exists(r.text, rd_shell.nav_desktop)
    assert _html.text_of(
        r.text, rd_dialogs.field_error(by_id("override-budget"), "amount")
    ).endswith("enter an amount of 0 or more")
    assert budgets_repo.get_default(db, USER_ID, cat_id) is None


def test_page_has_no_inline_style_and_loads_the_open_script(
    client: TestClient, cat_id: int
) -> None:
    r = client.get(_url(cat_id))

    assert not _html.exists(r.text, by_id("override-page-style"))
    script = _html.resolve_one(r.text, by_id("override-page-script"))
    assert str(script.get("src")).endswith("/rd/js/app-override-page.js")


def _page_form(client: TestClient, cat_id: int) -> dict[str, str]:
    """Fields a browser without scripts submits from the rendered full page (no token header)."""
    page = client.get(_url(cat_id))
    assert page.status_code == 200
    form = _html.form_of(page.text, plan.override_save)
    return dict(_html.submitted_fields(form))


def test_form_carries_the_csrf_token_for_a_script_free_post(
    raw_client: TestClient, cat_id: int
) -> None:
    fields = _page_form(raw_client, cat_id)

    assert fields["_csrf_token"] == raw_client.cookies.get("__Host-csrf")
    assert fields["tier"] == "default"


def test_script_free_form_post_saves_the_default_and_audits_it(
    raw_client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    fields = _page_form(raw_client, cat_id)
    fields["amount"] = "123.45"
    other = seed_login_user(db, user_id=2, email="other@example.com")
    before = audit_total(db)

    r = raw_client.post(f"/budget/rules/{cat_id}/overrides", data=fields)

    assert r.status_code == 200
    stored = budgets_repo.get_default(db, USER_ID, cat_id)
    assert stored is not None
    assert stored.amount == 12345
    assert audit_total(db) == before + 1
    assert audit_count(db, "budget_default") == 1
    assert budgets_repo.list_defaults(db, other) == []


def test_script_free_form_post_with_a_bad_amount_rerenders_the_page(
    raw_client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    fields = _page_form(raw_client, cat_id)
    fields["amount"] = "abc"
    before = audit_total(db)

    r = raw_client.post(f"/budget/rules/{cat_id}/overrides", data=fields)

    assert r.status_code == 422
    assert _html.exists(r.text, rd_shell.nav_desktop)
    assert _html.text_of(
        r.text, rd_dialogs.field_error(by_id("override-budget"), "amount")
    ).endswith("enter an amount of 0 or more")
    assert budgets_repo.get_default(db, USER_ID, cat_id) is None
    assert audit_total(db) == before
