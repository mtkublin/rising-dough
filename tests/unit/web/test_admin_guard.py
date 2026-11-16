"""T-D17 — admin guard helpers (ADR-0073 §1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from budget_planner.web.middleware.admin import is_admin_path, is_admin_user
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.routers.settings_users import current_admin


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/settings/users", True),
        ("/settings/users/", True),
        ("/settings/users/3/edit", True),
        ("/settings/usersX", False),
        ("/settings", False),
        ("/auth/sessions", False),
    ],
)
def test_is_admin_path(path: str, expected: bool) -> None:
    assert is_admin_path(path) is expected


def _user(*, admin: bool) -> CurrentUser:
    return CurrentUser(id=7, email="a@x.test", name="a", is_admin=admin, must_change_password=False)


def test_is_admin_user() -> None:
    assert is_admin_user(_user(admin=True)) is True
    assert is_admin_user(_user(admin=False)) is False
    assert is_admin_user(None) is False


def _request(user: CurrentUser | None) -> object:
    return SimpleNamespace(state=SimpleNamespace(user=user))


def test_current_admin_returns_admin() -> None:
    admin = _user(admin=True)
    assert current_admin(_request(admin)) is admin  # type: ignore[arg-type]


def test_current_admin_404s_members() -> None:
    with pytest.raises(HTTPException) as exc:
        current_admin(_request(_user(admin=False)))  # type: ignore[arg-type]
    assert exc.value.status_code == 404
