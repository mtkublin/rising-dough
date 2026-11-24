"""Auth surface against the handoff markup (``pages/auth/login.html``, ``reauth.html``).

The app renders the same markup, so the names are the app's.
"""

from __future__ import annotations

from tests.ui_map.auth import (
    email,
    login_error,
    login_heading,
    passkey_sign_in,
    password,
    reauth_cancel,
    reauth_confirm,
    reauth_error,
    reauth_heading,
    reauth_passkey,
    reauth_password,
    sign_in,
)

__all__ = [
    "email",
    "login_error",
    "login_heading",
    "passkey_sign_in",
    "password",
    "reauth_cancel",
    "reauth_confirm",
    "reauth_error",
    "reauth_heading",
    "reauth_passkey",
    "reauth_password",
    "sign_in",
]
