"""T-UR06 follow-up (UR06b, ADR-0107): the 422 "back to the form" link never leaves the origin.

``_back_url`` is private, so the cases go through the public path: a malformed query
parameter renders the 422 page and the test reads the back link ``href`` from the body.
A browser reads ``/\\evil`` as ``//evil``, so a backslash (raw or ``%5C``) or a control
character in the Referer path must fall back to ``/today``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.app import create_app
from tests.auth_support import login_cookie
from tests.ui_map import _html, errors

BAD_PARAM_URL = "/budget?month=zz"
TODAY = "/today"


@pytest.fixture
def back_client(tmp_path: Path) -> Iterator[TestClient]:
    db_url = f"sqlite:///{(tmp_path / 'back_url.sqlite').as_posix()}"
    cfg = Settings(_env_file=None, database_url=db_url)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    app = create_app(settings=cfg)
    cookie = login_cookie(cfg)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set(*cookie)
        yield c


def _back_href(client: TestClient, referer: str | None) -> str:
    headers = {} if referer is None else {"Referer": referer}
    r = client.get(BAD_PARAM_URL, headers=headers)
    assert r.status_code == 422
    href = _html.resolve_one(r.text, errors.form_link)["href"]
    assert isinstance(href, str)
    return href


@pytest.mark.parametrize(
    ("referer", "expected"),
    (
        # same-origin path and query are kept
        ("http://testserver/budget?month=2026-10", "/budget?month=2026-10"),
        ("http://testserver/ledger", "/ledger"),
        # foreign host falls back
        ("https://evil.example/budget?month=2026-10", TODAY),
        # protocol-relative path falls back
        ("http://testserver//evil.example", TODAY),
        ("http://testserver//evil.example/budget", TODAY),
        # backslash forms: a browser reads "/\\evil" as "//evil"
        ("http://testserver/\\evil.example", TODAY),
        ("http://testserver/\\\\evil.example", TODAY),
        ("http://testserver/%5Cevil", TODAY),
        ("http://testserver/%5cevil", TODAY),
        ("http://testserver/%5Cevil.example/budget", TODAY),
        # control characters in the Referer fall back
        ("http://testserver/\t/evil.example", TODAY),
        ("http://testserver/budget\n", TODAY),
    ),
)
def test_back_link_is_same_origin_path_or_today(
    back_client: TestClient, referer: str, expected: str
) -> None:
    assert _back_href(back_client, referer) == expected


def test_missing_referer_falls_back_to_today(back_client: TestClient) -> None:
    assert _back_href(back_client, None) == TODAY
