"""Web harness on the scratch DB copy (never data/budget.sqlite)."""

from __future__ import annotations

import os

os.environ.setdefault("BUDGET_ENV", "test")

from _common import REPO, SCRATCH, USER_ID, fresh_conn  # noqa: E402, F401
import sys  # noqa: E402

sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.services import _passwords  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from budget_planner.web.middleware.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME  # noqa: E402
from tests.auth_support import FAST_ROUNDS, login_cookie  # noqa: E402

_passwords.DEFAULT_ROUNDS = FAST_ROUNDS


class Client(TestClient):
    def __init__(self, *a, **k):  # noqa: ANN002, ANN003
        k.setdefault("base_url", "https://testserver")
        k.setdefault("raise_server_exceptions", False)
        super().__init__(*a, **k)
        self.get("/healthz")

    def request(self, method, url, *a, **k):  # noqa: ANN001, ANN002, ANN003
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            tok = self.cookies.get(CSRF_COOKIE_NAME)
            if tok:
                h = dict(k.get("headers") or {})
                h.setdefault(CSRF_HEADER_NAME, tok)
                k["headers"] = h
        return super().request(method, url, *a, **k)


def make_client() -> tuple[Client, Settings]:
    """Call after fresh_conn() (which prepares the scratch DB)."""
    settings = Settings(_env_file=None, database_url=f"sqlite:///{SCRATCH.as_posix()}")
    app = create_app(settings)
    c = Client(app)
    name, value = login_cookie(settings, user_id=USER_ID)
    c.cookies.set(name, value)
    return c, settings
