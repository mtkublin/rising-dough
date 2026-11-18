#!/usr/bin/env python3
"""DRILL-2 passkey check (T-D135): register + sign in with a passkey on a drill host.

Drives Chromium (Playwright) with a CDP virtual authenticator against a running
instance: password sign-in -> (forced password rotation, when required) ->
register a passkey at /settings/security -> sign out -> sign in with the passkey.
Exit 0 and a one-line PASS summary on success, 1 on any failure.

The password is read from STDIN only (line 1 = current password, optional
line 2 = new password, used only when the server forces a rotation, e.g. the
first admin sign-in after the Terraform-provisioned password). It is never taken
from argv and never printed. Failure messages name the step, not the page text.

    <command that prints the password> | uv run python scripts/drill/passkey_check.py \\
        --base-url https://<host> --username <email>

Never point this at production: it adds a passkey to the account it signs in as.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from typing import TextIO
from urllib.parse import urlsplit

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    expect,
    sync_playwright,
)

EXIT_OK = 0
EXIT_FAIL = 1
TIMEOUT_MS = 20_000
PASSWORD_ROUTE = "/settings/password"  # noqa: S105  (a URL path, not a secret)
LOGIN_ROUTE = "/auth/login"
SECURITY_ROUTE = "/settings/security"
DEFAULT_LABEL = "drill virtual key"
MIN_PASSWORD_LEN = 12


class CheckError(Exception):
    """A named step failed. The message never contains page text or secrets."""


@dataclass(frozen=True)
class Credentials:
    current: str
    new: str | None


def read_credentials(stream: TextIO) -> Credentials:
    """Line 1 = current password; optional line 2 = new password for a forced rotation."""
    lines = stream.read().splitlines()
    if not lines or not lines[0]:
        raise CheckError("stdin: no password supplied (line 1)")
    new = lines[1] if len(lines) > 1 and lines[1] else None
    if new is not None and len(new) < MIN_PASSWORD_LEN:
        raise CheckError(f"stdin: new password must be at least {MIN_PASSWORD_LEN} characters")
    return Credentials(current=lines[0], new=new)


def validate_base_url(raw: str) -> str:
    """Return the origin without trailing slash; reject IP literals (no passkey RP ID)."""
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise CheckError("--base-url must be an http(s) URL with a host name")
    try:
        ip_address(parts.hostname)
    except ValueError:
        return f"{parts.scheme}://{parts.netloc}"
    raise CheckError("--base-url must use a host name: a passkey RP ID cannot be an IP address")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register and use a passkey on a drill host.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True, help="sign-in e-mail of the account")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="passkey label to register")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    return parser.parse_args(argv)


def _install_virtual_authenticator(context: BrowserContext, page: Page) -> None:
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


def _password_sign_in(page: Page, username: str, creds: Credentials, steps: list[str]) -> None:
    page.goto(LOGIN_ROUTE)
    page.fill('input[name="email"]', username)
    page.fill('input[name="password"]', creds.current)
    page.click('form button[type="submit"]:has-text("Sign in")')
    page.wait_for_load_state("networkidle")
    if LOGIN_ROUTE in page.url:
        raise CheckError("password sign-in was rejected")
    steps.append("password sign-in")
    if PASSWORD_ROUTE not in page.url:
        return
    if creds.new is None:
        raise CheckError("server forces a password rotation: pass the new password as stdin line 2")
    page.fill("#pw-current_password", creds.current)
    page.fill("#pw-new_password", creds.new)
    page.fill("#pw-confirm_password", creds.new)
    page.click("#password-form button[type=submit]:not([form])")
    page.wait_for_url(lambda url: PASSWORD_ROUTE not in url)
    steps.append("forced password rotation")


def _journey(page: Page, username: str, creds: Credentials, label: str, steps: list[str]) -> None:
    _password_sign_in(page, username, creds, steps)

    page.goto(SECURITY_ROUTE)
    page.fill('form[data-passkey-register] input[name="label"]', label)
    page.click('form[data-passkey-register] button[type="submit"]')
    page.wait_for_url(f"**{SECURITY_ROUTE}#passkeys")
    expect(page.locator("#passkeys")).to_contain_text(label)
    steps.append("passkey registered")

    page.locator('form[action="/auth/logout"] button').first.click()
    page.wait_for_url("**/auth/login**")
    steps.append("signed out")

    page.click("[data-passkey-login]")
    page.wait_for_url(lambda url: LOGIN_ROUTE not in url)
    page.goto(SECURITY_ROUTE)
    expect(page.locator("[data-passkey-register]")).to_be_visible()
    steps.append("passkey sign-in")


def run_check(
    base_url: str, username: str, creds: Credentials, label: str, *, headless: bool = True
) -> tuple[str, ...]:
    """Run the journey; return the completed step names or raise CheckError."""
    steps: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            context = browser.new_context(base_url=base_url)
            context.set_default_timeout(TIMEOUT_MS)
            page = context.new_page()
            _install_virtual_authenticator(context, page)
            try:
                _journey(page, username, creds, label, steps)
            except (PlaywrightError, AssertionError) as exc:
                after = steps[-1] if steps else "start"
                raise CheckError(f"failed after step '{after}': {type(exc).__name__}") from None
        finally:
            browser.close()
    return tuple(steps)


def main(argv: Sequence[str] | None = None, stdin: TextIO | None = None) -> int:
    args = parse_args(argv)
    try:
        creds = read_credentials(stdin if stdin is not None else sys.stdin)
        base_url = validate_base_url(args.base_url)
        steps = run_check(base_url, args.username, creds, args.label, headless=not args.headed)
    except CheckError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(f"PASS: {base_url} " + " -> ".join(steps))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
