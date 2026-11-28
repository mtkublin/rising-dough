"""User admin journeys: edit, reset, delete from the row menu (T-UT08b, T-UR14).

One-time secrets are only checked for presence; the DB effect is the new / rotated hash and flags.
The add-user and invite dialogs are T-UR20; the second user is seeded.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import settings

pytestmark = pytest.mark.e2e

NEW_EMAIL = "second@example.test"


def _seed_user(world: World) -> int:
    world.make_admin()
    world.write(
        "INSERT INTO users (name, email, password_hash, must_change_password) "
        "VALUES ('Sam', ?, 'seeded-hash', 0)",
        (NEW_EMAIL,),
    )
    user = int(world.scalar("SELECT id FROM users WHERE email = ?", (NEW_EMAIL,)))
    world.goto("/settings/users")
    return user


def test_own_row_has_no_menu_and_other_rows_do(world: World) -> None:
    user = _seed_user(world)
    expect(world.find(settings.user_row(user))).to_contain_text(NEW_EMAIL)
    expect(world.find(settings.user_menu(NEW_EMAIL))).to_have_count(1)
    expect(world.find(settings.user_menu("owner@example.test"))).to_have_count(0)


def test_admin_edits_a_users_name_and_role(world: World) -> None:
    user = _seed_user(world)
    world.find(settings.user_menu(NEW_EMAIL)).click()
    world.find(settings.edit_user_item(NEW_EMAIL)).click()
    expect(world.find(settings.edit_form)).to_be_visible()
    expect(world.find(settings.user_email)).to_have_value(NEW_EMAIL)
    world.find(settings.user_name).fill("Samantha")
    world.find(settings.user_is_admin).check(force=True)  # the radio is visually hidden
    world.find(settings.edit_save).click()

    row = world.wait_rows("SELECT * FROM users WHERE id = ? AND name = 'Samantha'", (user,))[0]
    assert (row["is_admin"], row["email"], row["deleted_at"]) == (1, NEW_EMAIL, None)
    assert world.audit_ops("users", user) == ["update"]
    expect(world.find(settings.edit_form)).to_have_count(0)
    expect(world.find(settings.user_row(user))).to_contain_text("admin")


def test_admin_resets_a_users_secret(world: World) -> None:
    user = _seed_user(world)
    before = world.scalar("SELECT password_hash FROM users WHERE id = ?", (user,))
    world.find(settings.user_menu(NEW_EMAIL)).click()
    world.find(settings.reset_user(NEW_EMAIL)).click()
    expect(world.find(settings.reset_dialog)).to_be_visible()
    world.find(settings.reset_confirm).click()

    world.wait_rows("SELECT 1 FROM users WHERE id = ? AND password_hash <> ?", (user, before))
    assert world.scalar("SELECT must_change_password FROM users WHERE id = ?", (user,)) == 1
    expect(world.find(settings.new_password_value)).not_to_be_empty()
    expect(world.find(settings.user_row(user))).to_contain_text("new password required")
    world.find(settings.one_time_done).click()
    expect(world.find(settings.one_time_dialog)).to_have_count(0)


def test_admin_deletes_a_user(world: World) -> None:
    user = _seed_user(world)
    world.find(settings.user_menu(NEW_EMAIL)).click()
    world.find(settings.remove_user(NEW_EMAIL)).click()
    expect(world.find(settings.delete_dialog)).to_be_visible()
    world.find(settings.delete_confirm).click()

    world.wait_rows("SELECT 1 FROM users WHERE id = ? AND deleted_at IS NOT NULL", (user,))
    expect(world.find(settings.user_row(user))).to_have_count(0)
    assert world.audit_ops("users", user) == ["delete"]
