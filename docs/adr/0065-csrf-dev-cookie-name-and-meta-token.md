# ADR-0065: CSRF Cookie Name Is Env-Dependent; HTMX Reads the Token From a `<meta>` Tag

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0033](0033-v3-auth-single-user-passkey.md) §4
- **Related**: T-D08, T-D08a

## Context

T-D08 implemented ADR-0033 §4 as a double-submit cookie named `__Host-csrf`. To make it work on plain-HTTP dev, the middleware drops the `Secure` attribute when `settings.env == "dev"`.

That combination is invalid. The `__Host-` prefix is a browser-enforced contract: a cookie with that prefix **must** carry `Secure`, `Path=/`, and no `Domain`, or the browser silently discards it. Under `just dev` (default `env=dev`) the browser therefore never stores the token, and every POST/PUT/PATCH/DELETE is rejected with `403 {"detail": "missing_cookie"}`. Editing or deleting a transaction from the Ledger fails.

The defect was masked because:

- integration tests run with `env=test` (cookie has `Secure`) and Starlette's `TestClient` does not enforce cookie-prefix rules;
- the e2e fixture parsed `Set-Cookie` and re-injected `Cookie: __Host-csrf=…` as an extra HTTP header, bypassing the browser's cookie jar.

## Decision

1. **Cookie name depends on env.**
   - `env == "dev"` → cookie `csrf`, no `Secure`. Plain-HTTP dev works in every browser.
   - every other env → cookie `__Host-csrf` with `Secure` (unchanged ADR-0033 §4 behaviour for prod / test).
   - Resolved by a single helper, `csrf_cookie_name(settings)`, in `web/middleware/csrf.py`. No other code hard-codes the name.
2. **HTMX extension reads the token from `<meta name="csrf-token">`** rendered by `base.html` from `request.state.csrf_token`, instead of parsing `document.cookie`. This means the JS does not need to know the cookie name. It also keeps working if the cookie later becomes `HttpOnly`.
3. **E2E tests exercise the real browser cookie path.** The fixture no longer injects a hand-built `Cookie` header. It only sets `X-CSRF-Token` for `page.request` seeding calls, using the value the browser stored.

## Consequences

- Dev is protected by the same double-submit check. Only the browser-side prefix hardening is absent, which is acceptable for a `127.0.0.1`-bound dev server.
- Prod and test behaviour is unchanged. Existing integration tests keep using `__Host-csrf`.
- A regression test pins that `env=dev` mints a cookie whose name does not start with `__Host-` and that carries no `Secure` attribute.

## Amendment 2026-11-22 (operator decision; T-Q289)

The CSRF token is bound to the session: an HMAC of the session id keyed by the cookie secret, rotated on login and logout. The double-submit check compares the `X-CSRF-Token` header (read from the meta tag) with the value recomputed for the current session, so a token from one session fails on another and a request without a session is refused on state-changing routes. The dev cookie-name rule above is unchanged.

Implementation (T-Q289): a token is `nonce || HMAC-SHA256(cookie_secret, "csrf-v1|" + context + "|" + nonce)` (`web/csrf_token.py`, constant-time compare). The context is the session id for a live session and a fixed pre-session value for anonymous requests (login and passkey pages, which therefore work before a session exists). The cookie must verify for the request's context and equal the header or form field; otherwise 403 `invalid_csrf`. A cookie that is missing, empty or stale is re-minted on the response. When a response sets or clears the session cookie (login, logout), the same response carries a freshly bound CSRF cookie, so earlier tokens (including a tab opened before login) are refused and the existing 403 flash ("Reload the page and try again", ADR-0143) is the reload path. The secret is `BUDGET_COOKIE_SECRET` (required in production, T-D03). A client `X-Request-Id` is echoed only if it matches `[A-Za-z0-9._-]{1,64}`, else a generated id is used.
