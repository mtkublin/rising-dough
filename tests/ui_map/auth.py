"""Auth surface: login, re-auth, logout (handoff markup, T-UR05).

The app renders the handoff auth pages, so ``tests.ui_map.mockup.auth``
re-exports these names. Handoff button labels carry brackets.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import label, role

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
