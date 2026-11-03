# ADR-0070: Auth Web Layer — Cookie Names, Unauthenticated Responses, Middleware Order

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0033](0033-v3-auth-single-user-passkey.md) §3 and §5 (as already amended by [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) and [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md))
- **Related**: T-D02b (web layer), [ADR-0065](0065-csrf-dev-cookie-name-and-meta-token.md) (CSRF dev cookie name), T-D09 (rate limit), T-D17 (admin guard), T-D18 (forced password change)

## Context

T-D02b wires the auth backend from ADR-0067 into the web app. ADR-0033/0061/0067 leave these points open, or settle them in a way that does not work:

1. ADR-0033 §3 names the session cookie `__Host-session`. That prefix needs `Secure`, and browsers drop the cookie on plain-HTTP dev. CSRF hit the same problem (ADR-0065).
2. ADR-0033 §3 asks for `SameSite=Strict`. With Strict, the browser leaves the cookie off any top-level navigation that starts on another site, such as a bookmark synced through a mail client or a link in a chat app. The user lands on the login page even though they have a live session.
3. ADR-0067 §1 recommends `itsdangerous` to sign the passkey challenge cookie. The package is not a dependency.
4. ADR-0033 §5 says HTMX requests get a 401 JSON body. On its own that leaves the user on a page whose swaps keep failing silently.
5. The CSRF and security-headers middlewares say they run "after RequestId", but `app.add_middleware` actually wraps outermost-last. The current registration order makes CSRF the outermost layer, so its 403s carry no request id and no security headers.

## Decision

### 1. Cookie names depend on env, like ADR-0065

| Cookie | `env == "dev"` | every other env |
|---|---|---|
| session | `session`, no `Secure` | `__Host-session`, `Secure` |
| passkey challenge | `passkey_challenge`, no `Secure` | `__Host-passkey-challenge`, `Secure` |

Both cookies are `HttpOnly`, `Path=/` and have no `Domain`. One module, `web/auth_cookies.py`, resolves the names. No other code hard-codes them.

### 2. Session cookie: `SameSite=Lax`, sliding `Max-Age`

- `SameSite=Lax` replaces ADR-0033's Strict. CSRF defence comes from the double-submit token (ADR-0033 §4), which every unsafe method must carry. Lax still withholds the cookie on cross-site POST, iframe and subresource requests.
- `Max-Age = session_lifetime_days × 86400`. Every authenticated response that does not set the cookie itself re-issues it, so the browser expiry follows the server-side sliding expiry (ADR-0067 §2).
- If a request carries a session cookie that is unknown, revoked or expired, the response deletes the cookie.
- A successful login revokes any session the browser already presented. This keeps a pre-planted cookie from surviving login (session fixation).

### 3. Challenge cookie: stdlib HMAC, 5-minute TTL, one purpose per cookie

The challenge cookie value is `base64url(json payload) "." base64url(HMAC-SHA256(cookie_secret, "passkey-challenge|" + payload))`. The payload is `{purpose: "register"|"login", user_id, challenge (b64url), iat}`. Verification checks the signature with `hmac.compare_digest`, then the purpose, then the user id for `register`, then `iat + 300 s > now`. The cookie is `SameSite=Strict` and `Max-Age=300`. The `*_finish` response clears it whether the ceremony succeeds or fails. Using `hmac` from the standard library avoids adding a dependency for about 30 lines of code.

### 4. Unauthenticated requests to protected routes

| Request | Response |
|---|---|
| `HX-Request: true` | `401 {"error": "unauthorized"}` plus `HX-Redirect: /auth/login?next=<path>`. The path comes from `HX-Current-URL` when it is same-origin, so htmx sends the whole page to the login screen. |
| `Accept` contains `application/json` and not `text/html` | `401 {"error": "unauthorized"}` |
| anything else | `302 Location: /auth/login?next=<path+query>` |

`next` only accepts a same-site relative path. It must start with a single `/`. It must not start with `//` or `/\`, must not contain a backslash or a control character, and must not carry a scheme or a netloc. It must not point back into `/auth/login`. Any other value falls back to `/`.

**Exempt** paths: `/health`, `/ready`, `/healthz`, `/static/*`, `/auth/login`, `/auth/login/begin`, `/auth/login/finish`. Every other `/auth/*` route (`logout`, `register*`, `sessions*`, `passkeys*`) requires a session. Exempt paths still hydrate `request.state.user` when a valid cookie is present, so `/auth/login` can send a user who is already logged in on to `next`. `/static/*` never touches the DB.

### 5. `request.state.user` shape

`request.state.user` is a frozen `CurrentUser(id, email, name, is_admin, must_change_password)`. It deliberately omits the password hash. `request.state.session_id` is the **raw** cookie value, which logout and the current-session check need. `get_request_ctx` puts `session_handle(session_id)` into `RequestCtx.session_id`, never the raw value (ADR-0067 §4). `current_user_id` raises 401 when `request.state.user` is missing, and the user-1 fallback is removed.

### 6. Middleware order (outermost first)

1. `RequestIdMiddleware`
2. `SecurityHeadersMiddleware`
3. `AuthRequiredMiddleware`
4. `CSRFMiddleware`
5. routers

Starlette's `add_middleware` puts each new layer *outside* the existing ones, so `create_app` registers them in reverse order: CSRF, Auth, SecurityHeaders, RequestId. Because RequestId and SecurityHeaders are outermost, every auth 302/401 and every CSRF 403 now carries `X-Request-Id` and the baseline headers. Auth runs before CSRF, so an anonymous POST to a protected route gets a login redirect rather than a CSRF 403. That 403 would wrongly suggest that the request could have succeeded. Future guards go between Auth and CSRF:

- T-D18 `MustChangePasswordMiddleware` reads `request.state.user.must_change_password`.
- T-D17's admin guard reads `request.state.user.is_admin`.

T-D09 rate limits attach to the `/auth/login*` routes themselves.

### 7. Session and passkey management UI

`/auth/sessions` never renders raw session ids. Each row is addressed by its handle. `POST /auth/sessions/{handle}/revoke` maps the handle back to a session id through `list_active_sessions(conn, user_id)`, so the lookup is scoped to the caller. An unknown handle, or one that belongs to another user, returns 404. Revoking the current session also clears the cookie and redirects to `/auth/login`. Passkeys are revoked through `POST /auth/passkeys/{id}/revoke`, which is user-scoped in the repository.

## Consequences

- Dev logins work over plain HTTP. Production keeps the `__Host-` hardening.
- Each authenticated response carries one `Set-Cookie` header for the refreshed session. This costs little and stops the browser from dropping a session the server still considers live.
- No new runtime dependency.
- Tests that build their own `TestClient` and call protected routes must sign in. `tests/integration/web/_auth_helpers.py` provides a helper that does this.
