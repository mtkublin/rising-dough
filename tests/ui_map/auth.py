"""Auth surface: login, re-auth, logout (handoff markup, T-UR05).

The app renders the handoff auth pages, so ``tests.ui_map.mockup.auth``
re-exports these names. Handoff button labels carry brackets.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import by_id, label, role

login_heading = role("heading", "Sign in", level=1, exact=True)
reauth_heading = role("heading", re.compile(r"^Confirm it.s you$"), level=1)
email = label("email", exact=True)
password = label("password", exact=True)
sign_in = role("button", re.compile(r"^\[ sign in \]$"))
passkey_sign_in = role("button", "sign in with a passkey")
login_error = role("alert")

reauth_password = label("current password", exact=True)
reauth_confirm = role("button", re.compile(r"^\[ confirm \]$"))
reauth_passkey = role("button", "confirm with a passkey")
reauth_cancel = role("link", "cancel", exact=True)
reauth_error = role("alert")

# First-run /setup (T-UR21; no handoff page, derived from force-password).
setup_heading = role("heading", "Create the first account", level=1, exact=True)
setup_name = label("name", exact=True)
setup_email = label("email", exact=True)
setup_password = label("password", exact=True)
setup_confirm = label("confirm password", exact=True)
setup_create = role("button", re.compile(r"^\[ create account \]$"))
setup_token = by_id("setup-token")
setup_alert = role("alert")
setup_email_error = by_id("setup-email-error")
setup_password_error = by_id("setup-password-error")
setup_confirm_error = by_id("setup-confirm-error")


# Invite landing (T-UR20a; handoff auth/invite and its expired, used, invalid states).
invite_heading = role("heading", "Create your account", level=1, exact=True)
invite_email = label("email", exact=True)
invite_name = label("name", exact=True)
invite_password = label("password", exact=True)
invite_confirm = label("confirm password", exact=True)
invite_create = role("button", re.compile(r"^\[ create account \]$"))
invite_alert = role("alert")
invite_back = role("link", "back to sign in")
invite_caption = by_id("invite-caption")
invite_name_error = by_id("inv-name-error")
invite_password_error = by_id("inv-password-error")
invite_confirm_error = by_id("inv-confirm-error")
