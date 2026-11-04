"""T-D47 — passkey journey with a CDP virtual authenticator.

Registers a passkey from Settings → Security, signs out, then signs in with
the passkey. WebAuthn requires a hostname RP ID, so the browser talks to
``http://localhost:<port>`` (an IP literal such as 127.0.0.1 can never host a
passkey). The dev server derives the RP ID / origin from the request host
when ``BUDGET_WEBAUTHN_*`` are unset (ADR-0075).
"""

from __future__ import annotations

import sqlite3
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


def _age_sessions(db_path: Path) -> None:
    """Move every session's ``authenticated_at`` far into the past (scratch DB only)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE sessions SET authenticated_at = '2000-01-01T00:00:00.000000Z'")
        conn.commit()
    finally:
        conn.close()


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


def _add_passkey(page: Page, label: str) -> None:
    page.fill('form[data-passkey-register] input[name="label"]', label)
    page.click('form[data-passkey-register] button[type="submit"]')


def test_stale_session_adds_passkey_after_password_reauth(
    localhost_page: Page, live_server: tuple[str, Path]
) -> None:
    """Forced-stale window: the guarded add bounces to /auth/reauth, then succeeds."""
    page = localhost_page
    _password_login(page)
    page.goto("/settings/security")
    page.wait_for_load_state("networkidle")
    _age_sessions(live_server[1])

    _add_passkey(page, "Behind the gate")
    page.wait_for_url("**/auth/reauth**")
    expect(page.locator("[data-passkey-reauth]")).to_have_count(0)  # no passkey yet
    page.fill('input[name="password"]', TEST_PASSWORD)
    page.click('form[action="/auth/reauth"] button[type="submit"]')
    page.wait_for_url("**/settings/security")

    _add_passkey(page, "Behind the gate")
    page.wait_for_url("**/settings/security#passkeys")
    expect(page.locator("#passkeys")).to_contain_text("Behind the gate")


def test_stale_session_reauths_with_passkey(
    localhost_page: Page, live_server: tuple[str, Path]
) -> None:
    """With a passkey on file, the re-auth page offers it and a tap restores access."""
    page = localhost_page
    _password_login(page)
    page.goto("/settings/security")
    _add_passkey(page, "First key")
    page.wait_for_url("**/settings/security#passkeys")
    page.wait_for_load_state("networkidle")
    _age_sessions(live_server[1])

    page.goto("/settings/security")
    _add_passkey(page, "Second key")  # same authenticator: bounced before the ceremony
    page.wait_for_url("**/auth/reauth**")
    page.click("[data-passkey-reauth]")
    page.wait_for_url("**/settings/security")
    expect(page.locator("[data-passkey-register]")).to_be_visible()
    token = page.locator('meta[name="csrf-token"]').get_attribute("content") or ""
    resp = page.context.request.post("/auth/register/begin", headers={"X-CSRF-Token": token})
    assert resp.status == 200, "guard should pass right after passkey re-auth"


def test_ip_literal_host_explains_passkeys_need_localhost(
    page: Page, live_server: tuple[str, Path]
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/settings/security")
    page.click('form[data-passkey-register] button[type="submit"]')
    expect(page.locator("[data-passkey-status]")).to_contain_text("http://localhost")
