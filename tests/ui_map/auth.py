"""Auth surface: login, re-auth, logout."""

from __future__ import annotations

from tests.ui_map.locator import label, role

login_heading = role("heading", "Sign in", level=1)
reauth_heading = role("heading", "Confirm it's you", level=1)
email = label("Email")
password = label("Password")
sign_in = role("button", "Sign in")
