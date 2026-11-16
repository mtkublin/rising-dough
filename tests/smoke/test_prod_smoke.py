"""Post-deploy smoke journey (T-D43, ADR-0061 end to end).

ONE long Playwright journey run by a human against a deployed instance
(or a local scratch server). Never collected by default or in CI: the
``smoke`` marker is deselected in ``pyproject.toml`` addopts and the run
must opt in with ``-m smoke tests/smoke``.

Journey: admin signs in (rotating the Terraform-captured password when
forced) -> creates a second, non-admin user and captures the one-shot
password -> signs out -> second user signs in, is forced to rotate,
registers a passkey (CDP virtual authenticator), adds an account,
category and a transaction tagged with a random marker, sees it on
``/ledger`` -> signs out -> admin signs back in and asserts the marker is
NOT on the admin's ``/ledger`` (data isolation) -> reads
``/debug/audit-tail`` and finds the second user's transaction row with
payload "[other-user]" -> admin removes the smoke user (soft delete).

Environment (the test skips with a reason when any required one is unset):

- ``SMOKE_BASE_URL``            e.g. ``https://budget.example.com``
- ``SMOKE_ADMIN_EMAIL``         bootstrap admin email
- ``SMOKE_ADMIN_PASSWORD``      current admin password (the Terraform one on
  first run; if it no longer works the test falls back to the new one)
- ``SMOKE_ADMIN_NEW_PASSWORD``  password the admin rotates to (>= 12 chars)

Server-side requirements for the passkey step: ``BUDGET_WEBAUTHN_RP_ID``
and ``BUDGET_WEBAUTHN_ORIGIN`` must match ``SMOKE_BASE_URL`` (host and
origin). Chromium only treats ``localhost`` (not ``127.0.0.1``) as a valid
rp_id over plain HTTP, so locally use ``http://localhost:<port>`` with
``BUDGET_ENV=dev`` (ADR-0070 dev cookie names: ``session`` / ``csrf``
instead of ``__Host-*``, no ``Secure`` flag).

Rate limits (ADR-0072): the journey makes 4 password sign-ins (5 if the
admin password must fall back), well below the per-IP and per-email caps.

Run::

    SMOKE_BASE_URL=... SMOKE_ADMIN_EMAIL=... SMOKE_ADMIN_PASSWORD=... \\
    SMOKE_ADMIN_NEW_PASSWORD=... uv run pytest -m smoke tests/smoke -v --no-cov
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect, sync_playwright

pytestmark = pytest.mark.smoke

_REQUIRED = (
    "SMOKE_BASE_URL",
    "SMOKE_ADMIN_EMAIL",
    "SMOKE_ADMIN_PASSWORD",
    "SMOKE_ADMIN_NEW_PASSWORD",
)
_TIMEOUT_MS = 15_000
_PW_ROUTE = "/settings/password"


@pytest.fixture(scope="module")
def smoke_env() -> dict[str, str]:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        pytest.skip(f"smoke journey needs env vars: {', '.join(missing)}")
    env = {k: os.environ[k] for k in _REQUIRED}
    env["SMOKE_BASE_URL"] = env["SMOKE_BASE_URL"].rstrip("/")
    return env


@pytest.fixture(scope="module")
def browser(smoke_env: dict[str, str]) -> Iterator[Browser]:
    pw: Playwright
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Chromium is not installed: {exc}")
        try:
            yield br
        finally:
            br.close()


def _new_context(browser: Browser, base: str) -> BrowserContext:
    ctx = browser.new_context(base_url=base)
    ctx.set_default_timeout(_TIMEOUT_MS)
    return ctx


def _csrf(page: Page) -> str:
    token = page.locator('meta[name="csrf-token"]').get_attribute("content")
    assert token, "page has no csrf-token meta tag"
    return token


def _post(page: Page, path: str, **form: str | float | bool) -> None:
    """Form POST sharing the page's cookie jar, with the CSRF header (ADR-0065)."""
    resp = page.context.request.post(
        path, form=form, headers={"X-CSRF-Token": _csrf(page)}, max_redirects=0
    )
    assert resp.status < 400, f"POST {path} -> {resp.status}: {resp.text()[:300]}"


def _sign_in(page: Page, email: str, password: str) -> bool:
    """Submit the password form. True when a session was granted."""
    page.goto("/auth/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]:has-text("Sign in")')
    page.wait_for_load_state("networkidle")
    return "/auth/login" not in page.url


def _sign_out(page: Page) -> None:
    _post(page, "/auth/logout")
    page.goto("/auth/login")
    expect(page.locator("#login-heading")).to_be_visible()


def _rotate_password(page: Page, current: str, new: str) -> None:
    expect(page).to_have_url(re.compile(re.escape(_PW_ROUTE)))
    page.fill("#pw-current_password", current)
    page.fill("#pw-new_password", new)
    page.fill("#pw-confirm_password", new)
    page.click("#password-form button[type=submit]:not([form])")
    page.wait_for_url(lambda url: _PW_ROUTE not in url)


def _admin_sign_in(page: Page, env: dict[str, str]) -> str:
    """Sign the admin in, rotating if forced. Returns the password now in effect."""
    email, old, new = (
        env["SMOKE_ADMIN_EMAIL"],
        env["SMOKE_ADMIN_PASSWORD"],
        env["SMOKE_ADMIN_NEW_PASSWORD"],
    )
    current = old
    if not _sign_in(page, email, old):
        # Already rotated by a previous run.
        assert _sign_in(page, email, new), "admin could not sign in with either password"
        return new
    if _PW_ROUTE in page.url:
        _rotate_password(page, old, new)
        current = new
    return current


def _create_smoke_user(page: Page, email: str) -> str:
    page.goto("/settings/users")
    page.fill('form[action="/settings/users"] input[name="email"]', email)
    page.fill('form[action="/settings/users"] input[name="name"]', "Smoke User")
    page.click('form[action="/settings/users"] button[type="submit"]')
    pre = page.locator("#new-password-value")
    expect(pre).to_be_visible()
    password = pre.inner_text().strip()
    assert password, "one-shot password toast was empty"
    return password


def _register_passkey(page: Page) -> None:
    cdp = page.context.new_cdp_session(page)
    cdp.send("WebAuthn.enable")
    added = cdp.send(
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
    page.goto("/settings/security")
    page.fill('input[name="label"]', "smoke virtual key")
    page.click("form[data-passkey-register] button[type=submit]")
    page.wait_for_url(lambda url: url.endswith("/settings/security#passkeys"))
    expect(page.locator("#passkeys")).to_contain_text("smoke virtual key")
    creds: dict[str, Any] = cdp.send(
        "WebAuthn.getCredentials",
        {"authenticatorId": added["authenticatorId"]},
    )
    assert creds["credentials"], "virtual authenticator holds no credential"


def _add_transaction(page: Page, marker: str) -> None:
    _post(page, "/accounts", name=f"Smoke acct {marker}", currency="PLN", opening_balance="100.00")
    _post(page, "/categories", name=f"Smoke cat {marker}", direction="expense")
    page.goto("/accounts")
    account_id = _id_suffix(page.locator("tr[id^='account-']").first, "account-")
    page.goto("/categories")
    category = page.locator("[id^='category-']", has_text=f"Smoke cat {marker}").first
    category_id = _id_suffix(category, "category-")
    _post(
        page,
        "/transactions",
        operation_date=datetime.now(UTC).date().isoformat(),
        category_id=category_id,
        account_id=account_id,
        amount="12.34",
        description=marker,
    )


def _id_suffix(locator: Any, prefix: str) -> str:
    value = locator.get_attribute("id")
    assert value, f"no id attribute (prefix {prefix!r})"
    return str(value).removeprefix(prefix)


def _reauth(page: Page, password: str, next_path: str) -> None:
    """Exercise the step-up page (ADR-0076 §2) with the current password."""
    page.goto(f"/auth/reauth?next={next_path}")
    expect(page.locator("#reauth-heading")).to_be_visible()
    page.fill('input[name="password"]', password)
    page.click('form[action="/auth/reauth"] button[type="submit"]')
    page.wait_for_url(lambda url: "/auth/reauth" not in url)


def _remove_smoke_user(page: Page, email: str, password: str) -> None:
    _reauth(page, password, "/settings/users")
    page.goto("/settings/users")
    row = page.locator("tr[id^='user-row-']", has_text=email)
    expect(row).to_have_count(1)
    page.once("dialog", lambda dialog: dialog.accept())
    row.locator('form[action$="/delete"] button').click()
    expect(page.locator("tr[id^='user-row-']", has_text=email)).to_have_count(0)


def test_post_deploy_journey(browser: Browser, smoke_env: dict[str, str]) -> None:
    base = smoke_env["SMOKE_BASE_URL"]
    marker = f"smoke-{secrets.token_hex(6)}"
    user_email = f"{marker}@smoke.test"
    user_new_password = f"Sm0ke-{secrets.token_urlsafe(18)}"

    # 1-3. Admin signs in (rotating if forced) and creates the second user.
    admin_ctx = _new_context(browser, base)
    admin = admin_ctx.new_page()
    admin_password = _admin_sign_in(admin, smoke_env)
    one_shot_password = _create_smoke_user(admin, user_email)
    _sign_out(admin)

    user_removed = False
    try:
        # 4-8. Second user: forced rotation, passkey, account + transaction.
        user_ctx = _new_context(browser, base)
        user = user_ctx.new_page()
        assert _sign_in(user, user_email, one_shot_password), "new user could not sign in"
        expect(user).to_have_url(re.compile(re.escape(_PW_ROUTE)))
        _rotate_password(user, one_shot_password, user_new_password)
        _register_passkey(user)
        _add_transaction(user, marker)
        user.goto("/ledger")
        expect(user.get_by_text(marker).first).to_be_visible()
        _sign_out(user)
        user_ctx.close()

        # 9-10. Admin returns: the user's data must not leak across accounts.
        assert _sign_in(admin, smoke_env["SMOKE_ADMIN_EMAIL"], admin_password)
        admin.goto("/ledger")
        expect(admin.locator("body")).not_to_contain_text(marker)

        # 11. Audit trail carries the user's transaction.
        resp = admin.context.request.get("/debug/audit-tail?n=100")
        assert resp.ok, f"/debug/audit-tail -> {resp.status}"
        entries = resp.json()["entries"]
        other = [
            e for e in entries if e["entity_type"] == "transactions" and e["new"] == "[other-user]"
        ]
        assert other, "second user's transaction audit row missing or payload not scoped"
        assert marker not in json.dumps(entries), "other user's payload leaked via audit tail"
        assert "password_hash" not in resp.text()

        # 12. Cleanup: soft-delete the smoke user.
        _remove_smoke_user(admin, user_email, admin_password)
        user_removed = True
    finally:
        if not user_removed:
            try:
                if "/auth/login" in admin.url:
                    _sign_in(admin, smoke_env["SMOKE_ADMIN_EMAIL"], admin_password)
                _remove_smoke_user(admin, user_email, admin_password)
            except Exception as exc:
                print(f"[smoke] cleanup of {user_email} failed, remove it by hand: {exc}")
        admin_ctx.close()
