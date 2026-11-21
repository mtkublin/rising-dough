"""Auth surface: login, re-auth, logout."""

from __future__ import annotations

from tests.ui_map.locator import label, role

login_heading = role("heading", "Sign in", level=1)
reauth_heading = role("heading", "Confirm it's you", level=1)
email = label("Email")
password = label("Password")
sign_in = role("button", "Sign in", exact=True)
passkey_sign_in = role("button", "Sign in with a passkey")
login_error = role("alert")

reauth_password = label("Current password")
reauth_confirm = role("button", "Confirm", exact=True)
reauth_passkey = role("button", "Confirm with passkey")
reauth_cancel = role("link", "Cancel")
reauth_error = role("alert")
