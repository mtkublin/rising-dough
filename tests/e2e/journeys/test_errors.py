"""Error pages reachable from the browser (T-UT08b).

404 renders the HTML error page (here: the admin-only Users tab for a regular
user). 403 CSRF is only ever a JSON body (``{"detail": "invalid_csrf"}``), so it
is checked as a fetch from the signed-in page, plus that nothing was written.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD
from tests.e2e.journeys._world import World
from tests.ui_map import auth, errors, today

pytestmark = pytest.mark.e2e

FETCH_NO_CSRF = """async () => {
  const r = await fetch('/categories', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'name=Sneaky&direction=expense',
  });
  return [r.status, await r.json()];
}"""


def test_admin_only_page_is_a_404_page_for_a_regular_user(world: World) -> None:
    world.goto("/settings/users")
    expect(world.find(errors.heading)).to_have_text("Not found")
    expect(world.find(errors.main)).to_contain_text("doesn't exist")
    assert world.scalar("SELECT is_admin FROM users WHERE id = 1") == 0

    world.find(errors.back_link).click()
    expect(world.find(today.heading)).to_be_visible()


def test_post_without_a_csrf_token_is_403_and_writes_nothing(anon_world: World) -> None:
    anon_world.goto("/auth/login")
    anon_world.find(auth.email).fill(TEST_EMAIL)
    anon_world.find(auth.password).fill(TEST_PASSWORD)
    anon_world.find(auth.sign_in).click()
    expect(anon_world.find(today.heading)).to_be_visible()
    before = anon_world.scalar("SELECT COUNT(*) FROM categories")

    status, body = anon_world.page.evaluate(FETCH_NO_CSRF)

    assert (status, body) == (403, {"detail": "invalid_csrf"})
    assert anon_world.scalar("SELECT COUNT(*) FROM categories") == before
    assert anon_world.scalar("SELECT COUNT(*) FROM categories WHERE name = 'Sneaky'") == 0
