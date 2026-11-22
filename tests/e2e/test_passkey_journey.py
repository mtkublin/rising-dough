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

from budget_planner.web.middleware.csrf import CSRF_DEV_COOKIE_NAME
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD
from tests.e2e import db_probe
from tests.ui_map import auth, settings, shell
from tests.ui_map.locator import to_playwright

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
    to_playwright(page, auth.email).fill(TEST_EMAIL)
    to_playwright(page, auth.password).fill(TEST_PASSWORD)
    to_playwright(page, auth.sign_in).click()
    page.wait_for_url(lambda url: "/auth/login" not in url)


def test_register_then_sign_in_with_passkey(
    localhost_page: Page, live_server: tuple[str, Path]
) -> None:
    page = localhost_page
    _password_login(page)

    page.goto("/settings/security")
    _add_passkey(page, "Virtual key")
    page.wait_for_url("**/settings/security#passkeys")
    expect(to_playwright(page, settings.passkeys)).to_contain_text("Virtual key")
    assert (
        db_probe.scalar(
            live_server[1],
            "SELECT COUNT(*) FROM webauthn_credentials WHERE label = 'Virtual key'"
            " AND deleted_at IS NULL",
        )
        == 1
    )

    to_playwright(page, shell.sign_out).first.click()
    page.wait_for_url("**/auth/login**")

    to_playwright(page, auth.passkey_sign_in).click()
    page.wait_for_url(lambda url: "/auth/login" not in url)
    expect(to_playwright(page, auth.login_error)).to_have_count(0)
    # DB: signing in with the passkey stamped its last use.
    assert (
        db_probe.scalar(
            live_server[1],
            "SELECT last_used_at IS NOT NULL FROM webauthn_credentials WHERE label = 'Virtual key'",
        )
        == 1
    )


def _add_passkey(page: Page, label: str) -> None:
    to_playwright(page, settings.passkey_label).fill(label)
    to_playwright(page, settings.add_passkey).click()


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
    expect(to_playwright(page, auth.reauth_passkey)).to_have_count(0)  # no passkey yet
    to_playwright(page, auth.reauth_password).fill(TEST_PASSWORD)
    to_playwright(page, auth.reauth_confirm).click()
    page.wait_for_url("**/settings/security")

    _add_passkey(page, "Behind the gate")
    page.wait_for_url("**/settings/security#passkeys")
    expect(to_playwright(page, settings.passkeys)).to_contain_text("Behind the gate")
    assert (
        db_probe.scalar(
            live_server[1],
            "SELECT COUNT(*) FROM webauthn_credentials WHERE label = 'Behind the gate'"
            " AND deleted_at IS NULL",
        )
        == 1
    )


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
    to_playwright(page, auth.reauth_passkey).click()
    page.wait_for_url("**/settings/security")
    expect(to_playwright(page, settings.add_passkey)).to_be_visible()
    token = next(
        (c["value"] for c in page.context.cookies() if c["name"] == CSRF_DEV_COOKIE_NAME), ""
    )
    resp = page.context.request.post("/auth/register/begin", headers={"X-CSRF-Token": token})
    assert resp.status == 200, "guard should pass right after passkey re-auth"


def test_ip_literal_host_explains_passkeys_need_localhost(
    page: Page, live_server: tuple[str, Path]
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/settings/security")
    to_playwright(page, settings.add_passkey).click()
    expect(to_playwright(page, settings.passkeys)).to_contain_text("http://localhost")
