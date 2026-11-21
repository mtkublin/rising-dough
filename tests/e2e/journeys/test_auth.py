"""Login, logout, re-auth, password change (T-UT08b).

Every journey asserts the screen result and the session / credential rows.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD
from tests.e2e.journeys._world import World
from tests.ui_map import auth, settings, shell, today

pytestmark = pytest.mark.e2e

NEW_SECRET = "a-brand-new-horse-battery"  # noqa: S105  # pragma: allowlist secret
LIVE_SESSIONS = "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL"
STALE = "2000-01-01T00:00:00.000000Z"


def _sign_in(world: World, secret: str) -> None:
    world.goto("/auth/login")
    world.find(auth.email).fill(TEST_EMAIL)
    world.find(auth.password).fill(secret)
    world.find(auth.sign_in).click()


def test_login_rejects_a_wrong_secret_then_accepts_the_right_one(anon_world: World) -> None:
    _sign_in(anon_world, "not-the-right-one")
    expect(anon_world.find(auth.login_error)).to_be_visible()
    expect(anon_world.find(auth.login_heading)).to_be_visible()
    assert anon_world.scalar("SELECT COUNT(*) FROM sessions") == 0

    anon_world.find(auth.password).fill(TEST_PASSWORD)
    anon_world.find(auth.sign_in).click()
    expect(anon_world.find(today.heading)).to_be_visible()
    assert anon_world.scalar(LIVE_SESSIONS) == 1


def test_logout_revokes_the_session_and_blocks_the_back_button(anon_world: World) -> None:
    _sign_in(anon_world, TEST_PASSWORD)
    expect(anon_world.find(today.heading)).to_be_visible()
    anon_world.settle()
    anon_world.find(shell.sign_out).click()

    expect(anon_world.find(auth.login_heading)).to_be_visible()
    assert anon_world.scalar(LIVE_SESSIONS) == 0
    anon_world.page.go_back()
    expect(anon_world.find(auth.login_heading)).to_be_visible()


def test_protected_page_redirects_to_login_and_returns_after_sign_in(anon_world: World) -> None:
    anon_world.page.goto(f"{anon_world.base_url}/ledger")
    expect(anon_world.find(auth.login_heading)).to_be_visible()
    anon_world.find(auth.email).fill(TEST_EMAIL)
    anon_world.find(auth.password).fill(TEST_PASSWORD)
    anon_world.find(auth.sign_in).click()
    expect(anon_world.page).to_have_url(re.compile(r"/ledger"))


def test_stale_session_is_sent_to_reauth_then_confirmed_with_the_secret(world: World) -> None:
    world.make_admin()
    world.write("UPDATE sessions SET authenticated_at = ?", (STALE,))
    world.goto("/settings/users")
    world.find(settings.user_email).fill("late@example.test")
    world.find(settings.create_user).click()

    expect(world.find(auth.reauth_heading)).to_be_visible()
    assert world.scalar("SELECT COUNT(*) FROM users WHERE email = 'late@example.test'") == 0
    world.find(auth.reauth_password).fill("wrong-wrong-wrong")
    world.find(auth.reauth_confirm).click()
    expect(world.find(auth.reauth_error)).to_be_visible()

    world.find(auth.reauth_password).fill(TEST_PASSWORD)
    world.find(auth.reauth_confirm).click()
    expect(world.find(settings.users_heading)).to_be_visible()
    fresh = world.rows("SELECT authenticated_at FROM sessions WHERE revoked_at IS NULL")
    assert fresh and all(r["authenticated_at"] > STALE for r in fresh)


def test_change_secret_rejects_a_wrong_current_one(world: World) -> None:
    before = world.scalar("SELECT password_hash FROM users WHERE id = 1")
    world.goto("/settings/security")
    world.find(settings.current_password).fill("not-my-current-one")
    world.find(settings.new_password).fill(NEW_SECRET)
    world.find(settings.confirm_password).fill(NEW_SECRET)
    world.find(settings.change_password_button).click()

    expect(world.find(settings.password_summary)).to_be_visible()
    assert world.scalar("SELECT password_hash FROM users WHERE id = 1") == before


def test_change_secret_then_sign_in_with_the_new_one(world: World) -> None:
    before = world.scalar("SELECT password_hash FROM users WHERE id = 1")
    world.goto("/settings/security")
    world.find(settings.current_password).fill(TEST_PASSWORD)
    world.find(settings.new_password).fill(NEW_SECRET)
    world.find(settings.confirm_password).fill(NEW_SECRET)
    world.find(settings.change_password_button).click()

    world.wait_rows("SELECT 1 FROM users WHERE id = 1 AND password_hash <> ?", (before,))
    expect(world.find(settings.security_heading)).to_be_visible()
    world.find(shell.sign_out).first.click()
    expect(world.find(auth.login_heading)).to_be_visible()

    _sign_in(world, TEST_PASSWORD)
    expect(world.find(auth.login_error)).to_be_visible()
    world.find(auth.password).fill(NEW_SECRET)
    world.find(auth.sign_in).click()
    expect(world.find(today.heading)).to_be_visible()
