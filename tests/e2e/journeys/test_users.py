"""User admin journeys: add, reset, delete (T-UT08b). One-time secrets are only
checked for presence; the DB effect is the new / rotated hash and flags."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import settings

pytestmark = pytest.mark.e2e

NEW_EMAIL = "second@example.test"


def _add_user(world: World) -> int:
    world.make_admin()
    world.goto("/settings/users")
    world.find(settings.user_email).fill(NEW_EMAIL)
    world.find(settings.create_user).click()
    expect(world.find(settings.new_password_toast)).to_be_visible()
    return int(world.wait_rows("SELECT id FROM users WHERE email = ?", (NEW_EMAIL,))[0]["id"])


def test_admin_adds_a_user_and_sees_the_one_time_secret(world: World) -> None:
    user = _add_user(world)

    expect(world.find(settings.new_password_value)).not_to_be_empty()
    row = world.rows("SELECT * FROM users WHERE id = ?", (user,))[0]
    assert (row["must_change_password"], row["is_admin"], row["deleted_at"]) == (1, 0, None)
    assert row["password_hash"]
    expect(world.find(settings.user_row(user))).to_contain_text(NEW_EMAIL)


def test_admin_resets_a_users_secret(world: World) -> None:
    user = _add_user(world)
    before = world.scalar("SELECT password_hash FROM users WHERE id = ?", (user,))
    world.find(settings.reset_user(NEW_EMAIL)).click()  # native confirm is accepted

    world.wait_rows("SELECT 1 FROM users WHERE id = ? AND password_hash <> ?", (user, before))
    assert world.scalar("SELECT must_change_password FROM users WHERE id = ?", (user,)) == 1
    expect(world.find(settings.new_password_value)).not_to_be_empty()


def test_admin_removes_a_user(world: World) -> None:
    user = _add_user(world)
    world.find(settings.remove_user(NEW_EMAIL)).click()

    expect(world.find(settings.user_row(user))).to_have_count(0)
    world.wait_rows("SELECT 1 FROM users WHERE id = ? AND deleted_at IS NOT NULL", (user,))
