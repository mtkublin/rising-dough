"""First-run /setup route contracts (T-UR21, ADR-0134 section 9, ADR-0106 section 1).

Pins status, redirect target, CSRF enforcement and the DB/audit effect. Markup
and field errors are asserted in ``tests/integration/web/test_setup_page.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.services.setup import hash_token
from tests.auth_support import TEST_PASSWORD
from tests.contract._audit import audit_count
from tests.contract.conftest import covers
from tests.db_template import sqlite_url

pytest_plugins = ["tests.contract._support"]

TOKEN = "-".join(("tok", "contract", "setup", "value"))
WRONG_TOKEN = "-".join(("not", "the", "token"))
EMAIL = "contract.admin@example.test"
FORM = {
    "token": TOKEN,
    "name": "Contract Admin",
    "email": EMAIL,
    "password": TEST_PASSWORD,
    "password_confirm": TEST_PASSWORD,
}


@pytest.fixture
def settings(migrated_db: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        database_url=sqlite_url(migrated_db),
        planner_setup_token_hash=hash_token(TOKEN),
    )


@covers("GET /setup")
def test_setup_form_is_public_404_without_token_and_redirects_when_closed(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    assert anon_client.get(f"/setup?token={TOKEN}").status_code == 200
    assert anon_client.get("/setup").status_code == 404
    assert anon_client.get(f"/setup?token={WRONG_TOKEN}").status_code == 404
    db.execute("UPDATE users SET email = 'u@example.test' WHERE id = 1")
    db.commit()
    r = anon_client.get(f"/setup?token={TOKEN}", follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/auth/login")


@covers("POST /setup")
def test_setup_submit_creates_admin_audits_and_signs_in(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    r = anon_client.post("/setup", data=FORM, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, "/today")
    row = db.execute("SELECT is_admin FROM users WHERE email = ?", (EMAIL,)).fetchone()
    assert row["is_admin"] == 1
    assert audit_count(db, "setup_token", "create") == 1
    assert audit_count(db, "users", "create") == 1


@covers("POST /setup")
def test_setup_submit_wrong_token_is_404_and_csrf_is_enforced(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    r = anon_client.post("/setup", data={**FORM, "token": WRONG_TOKEN}, follow_redirects=False)
    assert r.status_code == 404
    forged = anon_client.post(
        "/setup", data=FORM, headers={"X-CSRF-Token": "forged"}, follow_redirects=False
    )
    assert forged.status_code == 403
    assert audit_count(db, "setup_token") == 0
