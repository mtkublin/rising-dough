"""T-D47 — passkey journey with a CDP virtual authenticator.

Registers a passkey from Settings → Security, signs out, then signs in with
the passkey. WebAuthn requires a hostname RP ID, so the browser talks to
``http://localhost:<port>`` (an IP literal such as 127.0.0.1 can never host a
passkey). The dev server derives the RP ID / origin from the request host
when ``BUDGET_WEBAUTHN_*`` are unset (ADR-0075).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.e2e


def _virtual_authenticator(context: BrowserContext, page: Page) -> None:
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


@pytest.fixture
def localhost_page(_browser: Browser, live_server: tuple[str, Path]) -> Iterator[Page]:
    base_url, _ = live_server
    port = urlsplit(base_url).port
    context = _browser.new_context(base_url=f"http://localhost:{port}")
    page = context.new_page()
    _virtual_authenticator(context, page)
    try:
        yield page
    finally:
        context.close()


def _password_login(page: Page) -> None:
    page.goto("/auth/login")
    page.fill('input[name="email"]', TEST_EMAIL)
    page.fill('input[name="password"]', TEST_PASSWORD)
    page.locator('form button[type="submit"]').first.click()
    page.wait_for_url(lambda url: "/auth/login" not in url)


def test_register_then_sign_in_with_passkey(localhost_page: Page) -> None:
    page = localhost_page
    _password_login(page)

    page.goto("/settings/security")
    page.fill('form[data-passkey-register] input[name="label"]', "Virtual key")
    page.click('form[data-passkey-register] button[type="submit"]')
    page.wait_for_url("**/settings/security#passkeys")
    expect(page.locator("#passkeys")).to_contain_text("Virtual key")

    page.locator('form[action="/auth/logout"] button').first.click()
    page.wait_for_url("**/auth/login**")

    page.click("[data-passkey-login]")
    page.wait_for_url(lambda url: "/auth/login" not in url)
    expect(page.locator("body")).not_to_contain_text("didn't work")


def test_ip_literal_host_explains_passkeys_need_localhost(
    page: Page, live_server: tuple[str, Path]
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/settings/security")
    page.click('form[data-passkey-register] button[type="submit"]')
    expect(page.locator("[data-passkey-status]")).to_contain_text("http://localhost")
