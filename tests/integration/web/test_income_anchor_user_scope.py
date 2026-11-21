"""T-Q201 (Q-001): the income-anchor endpoint writes the signed-in user's preference only.

Ported from ``docs/plans/quality-audit/repro/H2/h2_01_anchor_oracle.py``: the endpoint used to be
bound to user 1, so any other user got a 200/422 oracle on user 1's category ids and could set
user 1's anchor (ADR-0025, ADR-0061, ADR-0022).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from budget_planner.services import preferences as preferences_svc
from budget_planner.web.app import create_app
from tests.auth_support import login_cookie
from tests.integration.web.conftest import _CSRFAwareTestClient

pytestmark = pytest.mark.integration

URL = "/budget/preferences/income-anchor"
FIRST_USER = 1
OTHER_USER = 2


@pytest.fixture
def user_two_client(_migrated: Settings) -> Iterator[TestClient]:
    name, value = login_cookie(_migrated, user_id=OTHER_USER, email="second@example.test")
    with _CSRFAwareTestClient(create_app(settings=_migrated)) as c:
        c.cookies.set(name, value)
        yield c


def _income(settings: Settings, user_id: int, name: str) -> int:
    conn = get_connection(settings)
    try:
        return categories_repo.create(
            conn, user_id, NewCategory(name=name, direction=Direction.INCOME)
        ).id
    finally:
        conn.close()


def _set_anchor(settings: Settings, user_id: int, category_id: int) -> None:
    conn = get_connection(settings)
    try:
        preferences_svc.set_income_anchor_category_id(conn, user_id, category_id)
    finally:
        conn.close()


def _anchor(settings: Settings, user_id: int) -> int | None:
    conn = get_connection(settings)
    try:
        return preferences_svc.get_income_anchor_category_id(conn, user_id)
    finally:
        conn.close()


def test_second_user_sets_own_anchor_and_leaves_user_one_untouched(
    user_two_client: TestClient, _migrated: Settings
) -> None:
    first_id = _income(_migrated, FIRST_USER, "U1 salary")
    own_id = _income(_migrated, OTHER_USER, "U2 salary")
    _set_anchor(_migrated, FIRST_USER, first_id)

    r = user_two_client.post(URL, data={"category_id": str(own_id)})

    assert r.status_code == 200
    assert _anchor(_migrated, OTHER_USER) == own_id
    assert _anchor(_migrated, FIRST_USER) == first_id


def test_second_user_gets_no_oracle_on_user_one_categories(
    user_two_client: TestClient, _migrated: Settings
) -> None:
    first_id = _income(_migrated, FIRST_USER, "U1 salary")

    r = user_two_client.post(URL, data={"category_id": str(first_id)})

    assert r.status_code == 422
    assert _anchor(_migrated, FIRST_USER) is None
    assert _anchor(_migrated, OTHER_USER) is None


def test_second_user_clearing_does_not_clear_user_one(
    user_two_client: TestClient, _migrated: Settings
) -> None:
    first_id = _income(_migrated, FIRST_USER, "U1 salary")
    _set_anchor(_migrated, FIRST_USER, first_id)

    r = user_two_client.post(URL, data={"category_id": ""})

    assert r.status_code == 200
    assert _anchor(_migrated, FIRST_USER) == first_id
