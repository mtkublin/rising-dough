"""``SessionRow.device_label`` for stored sessions (T-UR34h)."""

from __future__ import annotations

import sqlite3

from budget_planner.repositories import sessions as sessions_repo
from budget_planner.services import security_settings
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

_ABSOLUTE_DAYS = 30
_FIREFOX_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0"
)
_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def test_session_rows_carry_device_label_and_hide_other_user(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    del world_with_two_users
    mine = sessions_repo.create_session(conn, OWNER_ID, ip="10.0.0.1", user_agent=_FIREFOX_MAC)
    sessions_repo.create_session(conn, OWNER_ID, ip="10.0.0.3", user_agent=None)
    sessions_repo.create_session(conn, OTHER_ID, ip="10.0.0.2", user_agent=_SAFARI_IPHONE)

    view = security_settings.security_view(
        conn, OWNER_ID, session_token=mine.token, absolute_lifetime_days=_ABSOLUTE_DAYS
    )

    assert sorted((r.session.ip, r.device_label, r.is_current) for r in view.session_rows) == [
        ("10.0.0.1", "Firefox · macOS", True),
        ("10.0.0.3", "Unknown device", False),
    ]
