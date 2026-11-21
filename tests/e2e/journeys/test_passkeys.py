"""Passkey add and remove with a CDP virtual authenticator (T-UT08b).

Chromium only: Firefox and WebKit are strict xfails registered in
``journeys/conftest.py`` through ``BROWSER_XFAILS`` (ADR-0106 section 4).
Sign-in and re-auth with a passkey stay in ``tests/e2e/test_passkey_journey.py``.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD
from tests.e2e.journeys._world import World
from tests.ui_map import auth, settings, today

pytestmark = pytest.mark.e2e

LIVE_KEYS = "SELECT label FROM webauthn_credentials WHERE deleted_at IS NULL"


def _add_passkey(world: World, label: str) -> None:
    world.goto("/auth/login")
    world.find(auth.email).fill(TEST_EMAIL)
    world.find(auth.password).fill(TEST_PASSWORD)
    world.find(auth.sign_in).click()
    expect(world.find(today.heading)).to_be_visible()
    world.goto("/settings/security")
    world.find(settings.passkey_label).fill(label)
    world.find(settings.add_passkey).click()
    expect(world.find(settings.passkey_remove(label))).to_be_visible()


def test_add_a_passkey(passkey_world: World) -> None:
    _add_passkey(passkey_world, "Virtual key")

    rows = passkey_world.rows(LIVE_KEYS)
    assert [r["label"] for r in rows] == ["Virtual key"]
    expect(passkey_world.find(settings.passkeys)).to_contain_text("Virtual key")


def test_add_then_remove_a_passkey(passkey_world: World) -> None:
    _add_passkey(passkey_world, "Short lived")
    passkey_world.find(settings.passkey_remove("Short lived")).click()

    expect(passkey_world.find(settings.passkey_remove("Short lived"))).to_have_count(0)
    passkey_world.wait_rows(LIVE_KEYS, count=0)
    assert passkey_world.scalar("SELECT COUNT(*) FROM webauthn_credentials") == 1  # soft-deleted
