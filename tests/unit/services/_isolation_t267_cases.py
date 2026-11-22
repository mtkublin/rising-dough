"""Isolation cases for security_settings and settings_drawer (T-Q267).

Same world and conventions as ``_isolation_read_cases.py``: one user's view never shows the
other user's sessions, passkeys or categories.
"""

from __future__ import annotations

import sqlite3
from typing import cast

from budget_planner.domain.categories import Category
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import security_settings, settings_drawer
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

_ABSOLUTE_DAYS = 30


@covers("security_settings.security_view")
def _case_security_view(conn: sqlite3.Connection, world: World) -> None:
    owner = sessions_repo.create_session(conn, OWNER_ID, ip="10.0.0.1", user_agent="owner-ua")
    other = sessions_repo.create_session(conn, OTHER_ID, ip="10.0.0.2", user_agent="other-ua")
    for user_id, cred, label in (
        (OWNER_ID, b"owner-cred", "owner key"),
        (OTHER_ID, b"other-cred", "other key"),
    ):
        webauthn_repo.create_credential(
            conn,
            user_id=user_id,
            credential_id=cred,
            public_key=b"k",
            sign_count=0,
            label=label,
        )
    own = security_settings.security_view(
        conn, OWNER_ID, session_token=owner.token, absolute_lifetime_days=_ABSOLUTE_DAYS
    )
    theirs = security_settings.security_view(
        conn, OTHER_ID, session_token=owner.token, absolute_lifetime_days=_ABSOLUTE_DAYS
    )
    assert [(r.session.ip, r.is_current) for r in own.session_rows] == [("10.0.0.1", True)]
    assert [(r.session.ip, r.is_current) for r in theirs.session_rows] == [("10.0.0.2", False)]
    assert own.session_rows[0].session.handle == owner.session.handle
    assert theirs.session_rows[0].session.handle == other.session.handle
    assert [p.label for p in own.passkeys] == ["owner key"]
    assert [p.label for p in theirs.passkeys] == ["other key"]


@covers("settings_drawer.drawer_context")
def _case_drawer_context(conn: sqlite3.Connection, world: World) -> None:
    own = settings_drawer.drawer_context(conn, OWNER_ID, "categories")
    theirs = settings_drawer.drawer_context(conn, OTHER_ID, "categories")
    own_ids = {c.id for c in cast("list[Category]", own["categories"])}
    their_ids = {c.id for c in cast("list[Category]", theirs["categories"])}
    assert world.owner.category_id in own_ids
    assert world.owner.category_id not in their_ids
    assert world.other.category_id in their_ids
    assert world.other.category_id not in own_ids
    assert own["current_anchor_id"] == world.owner.income_category_id
    assert theirs["current_anchor_id"] == world.other.income_category_id
