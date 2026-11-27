"""Picker inline create route: auth, CSRF, DB and audit (T-UR68, ADR-0106).

The option markup and the duplicate message are in
``tests/integration/web/test_picker_create_category.py``.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tests.contract._audit import audit_count
from tests.contract.conftest import covers

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # client, raw_client, anon_client, db

_NAME = "Zzz Contract"


def _count(db: sqlite3.Connection) -> int:
    db.commit()  # end any read snapshot so the app's writes are visible
    row = db.execute("SELECT count(*) FROM categories WHERE name = ?", (_NAME,)).fetchone()
    return int(row[0])


@covers("POST /categories/picker")
def test_anonymous_post_is_refused_and_creates_nothing(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    r = anon_client.post("/categories/picker", data={"name": _NAME}, follow_redirects=False)
    assert r.status_code in (302, 401, 403)
    assert _count(db) == 0
    assert audit_count(db, "category", "create") == 0


@covers("POST /categories/picker")
def test_post_without_csrf_token_is_403_and_creates_nothing(
    raw_client: TestClient, db: sqlite3.Connection
) -> None:
    r = raw_client.post("/categories/picker", data={"name": _NAME})
    assert r.status_code == 403
    assert _count(db) == 0


@covers("POST /categories/picker")
def test_post_creates_one_category_row_and_one_audit_row(
    client: TestClient, db: sqlite3.Connection
) -> None:
    before = audit_count(db, "category", "create")
    r = client.post("/categories/picker", data={"name": _NAME})
    assert r.status_code == 200
    assert _count(db) == 1
    assert audit_count(db, "category", "create") == before + 1
