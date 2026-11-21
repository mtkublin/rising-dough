"""Fixtures for the UI-map journeys (T-UT08b). Reuses ``page`` / ``live_server``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

from tests.e2e.conftest import BROWSER_XFAILS
from tests.e2e.journeys._world import World

pytestmark = pytest.mark.e2e


@pytest.fixture
def world(page: Page, live_server: tuple[str, Path]) -> World:
    """Signed-in page with seeding helpers; native confirm dialogs are accepted."""
    base_url, db_path = live_server
    page.on("dialog", lambda d: d.accept())
    return World(page=page, base_url=base_url, db_path=db_path)


@pytest.fixture
def anon_page(_browser: Browser, live_server: tuple[str, Path]) -> Iterator[Page]:
    """A signed-out page (no session cookie) on the same live server."""
    base_url, _ = live_server
    context = _browser.new_context(base_url=base_url)
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


@pytest.fixture
def anon_world(anon_page: Page, live_server: tuple[str, Path]) -> World:
    """``World`` over the signed-out page (login / logout journeys)."""
    base_url, db_path = live_server
    anon_page.on("dialog", lambda d: d.accept())
    return World(page=anon_page, base_url=base_url, db_path=db_path)


# --- passkeys: CDP virtual authenticator is Chromium-only (ADR-0106 section 4) --
_CDP_ONLY = "journey drives a CDP virtual WebAuthn authenticator (Chromium-only API)"
for _browser_name in ("firefox", "webkit"):
    for _name in ("test_add_a_passkey", "test_add_then_remove_a_passkey"):
        BROWSER_XFAILS[(_browser_name, f"journeys/test_passkeys.py::{_name}")] = _CDP_ONLY


@pytest.fixture
def passkey_world(_browser: Browser, live_server: tuple[str, Path]) -> Iterator[World]:
    """Signed-out ``World`` on ``localhost`` plus a virtual authenticator."""
    base_url, db_path = live_server
    port = urlsplit(base_url).port
    localhost = f"http://localhost:{port}"
    context = _browser.new_context(base_url=localhost)
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    cdp.send(
        "WebAuthn.addVirtualAuthenticator",
        {
            "options": {
                "protocol": "ctap2",
                "transport": "internal",
                "hasResidentKey": True,
                "hasUserVerification": True,
                "isUserVerified": True,
                "automaticPresenceSimulation": True,
            }
        },
    )
    try:
        yield World(page=page, base_url=localhost, db_path=db_path)
    finally:
        context.close()
