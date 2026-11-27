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
from tests.contract.test_plan_support import USER_ID
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
    assert "rd/js/app-override-page.js" in r.text
