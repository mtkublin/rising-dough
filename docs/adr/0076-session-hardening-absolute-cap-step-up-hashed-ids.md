# ADR-0076: Session Hardening — Absolute Lifetime Cap, Step-Up Re-Auth, Hashed Session Ids

- **Status**: Accepted
- **Date**: 2026-11-04
- **Amends**: [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md) §2 and Consequences (raw ids in the DB), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) §2 (cookie `Max-Age`), §3 (challenge purposes)
- **Related**: T-D53 (implementation), [ADR-0072](0072-auth-rate-limit-sqlite-fixed-window.md) (rate limits), [ADR-0074](0074-password-change-policy-and-forced-rotation.md) (password change), [ADR-0075](0075-security-controls-live-in-settings.md) (Security tab), [ADR-0071](0071-production-startup-migrations.md) (N-1 migration policy)

## Context

v3 authenticates with opaque server-side sessions (ADR-0067 §2): a 256-bit random id in an `HttpOnly`, `Secure`, `__Host-` cookie, looked up on every request. Expiry slides forward 14 days on each request. We considered short-lived access tokens with refresh tokens and rejected them. That pattern exists to make stateless tokens revocable. Our sessions are already stateful and can be revoked instantly. In a same-origin cookie app, both tokens would also sit in the same cookie jar, so anything that steals one steals the other.

The review behind this ADR found four gaps in the current design. Each one makes a stolen session cookie more valuable:

1. **No absolute lifetime.** Expiry slides, so an attacker who keeps using a stolen cookie keeps the session alive indefinitely.
2. **No step-up re-authentication.** A hijacked session can register the attacker's own passkey, revoke the victim's passkeys and sessions, or (as an admin) reset other users' passwords. The attacker turns a temporary foothold into permanent account takeover and locks the owner out.
3. **Raw session ids stored in the DB.** ADR-0067 accepted this. But a leaked DB file or backup (Litestream replica, `VACUUM INTO` pre-migration backup, restore-drill copy) then yields live bearer tokens. With hashed ids the leak exposes data but gives no way to impersonate a user.
4. **Session id never changes**, including when the session gains privilege through re-auth.

## Decision

### 1. Absolute session lifetime

- New setting `session_absolute_lifetime_days`, default **30**, range 1–365. A settings validator rejects a value lower than `session_lifetime_days`.
- A session's effective expiry is `min(last_seen_at + session_lifetime_days, created_at + session_absolute_lifetime_days)`. `touch_session` clamps `expires_at` to the absolute bound, so `expires_at` stays the single column `get_session` checks.
- The absolute bound comes from `created_at`, which already exists. No new column is needed, and sessions created by an N-1 image are capped as well.
- The cookie `Max-Age` follows the clamped `expires_at` (amends ADR-0070 §2), so the browser drops the cookie when the server does.
- When the cap is reached the session ends and the user follows the normal login flow, `next` included. On their own devices that means about one passkey tap per month.
- The Security sessions list shows each session's absolute expiry ("expires on …").

### 2. Step-up re-authentication for account-takeover actions

- New nullable column `sessions.authenticated_at`: when the session holder last proved a credential. A login sets it, and so does a successful re-auth or password change. `NULL`, for rows from before this migration, is read as `created_at`.
- New setting `session_reauth_window_minutes`, default **10**, range 1–60.
- A FastAPI dependency `require_recent_auth` runs at route level, like the ADR-0072 rate limits. It passes when `now - authenticated_at <= window`. The middleware order from ADR-0070 §6 is unchanged.
- **Guarded routes**:
  - `POST /auth/register/begin`, `POST /auth/register/finish` (add a passkey)
  - `POST /auth/passkeys/{id}/revoke`
  - `POST /auth/sessions/{handle}/revoke` when the target is **not** the current session. Revoking your own session is logout and stays unguarded.
  - every `POST` under `/settings/users` (admin create, edit, reset password, delete)
- **Not guarded**:
  - `POST /settings/password` already requires the current password, which is a step-up in itself. Success refreshes `authenticated_at`.
  - CSV exports (`GET /transactions/export`, `GET /planned/export`). A hijacked session can read every page anyway, so gating bulk export adds friction without changing what the attacker can reach.
- **Stale responses**, following the shape of ADR-0070 §4:

  | Request | Response |
  |---|---|
  | `HX-Request: true` | `403 {"error": "reauth_required"}` + `HX-Redirect: /auth/reauth?next=<HX-Current-URL path>` |
  | JSON (`passkeys.js`) | `403 {"error": "reauth_required", "redirect": "/auth/reauth?next=<page>"}`. `passkeys.js` navigates to `redirect`. |
  | anything else | `303 Location: /auth/reauth?next=<path>` |

  `next` is validated with the same rules as ADR-0070 §4.
- **Re-auth page** `GET /auth/reauth` (session required, not exempt):
  - **Passkey** (preferred): `POST /auth/reauth/begin` + `POST /auth/reauth/finish`. Unlike usernameless login, `allowCredentials` lists the session user's own credentials, and `finish` rejects a credential owned by anyone else. The challenge cookie gets a third purpose, `"reauth"` (amends ADR-0070 §3), bound to `user_id`.
  - **Password**: `POST /auth/reauth` with the current password.
  - Rate limited under scope `reauth`, per user, 5 / min + 20 / hour (ADR-0072 limiter, `BUDGET_RATE_LIMIT_REAUTH_*`).
  - Success and failure are audited (`entity_type='auth_event'`, `operation='create'`, `new={event: "reauth" | "reauth_failed", method, reason?}`, session handle via `RequestCtx`).
  - On success the server sets `authenticated_at = now`, **rotates the session id** (§4), and redirects to `next`.

### 3. Session ids hashed at rest

- The cookie carries a **token**, `secrets.token_urlsafe(32)` as before. `sessions.id` stores `sha256(token)` as lowercase hex. The raw token exists only in the `Set-Cookie` response and in the browser.
- `create_session` returns the raw token alongside the `Session` row (`IssuedSession(session, token)`). Every lookup (`get_session`, `touch_session`, `revoke_session`) takes the token and hashes it before the query.
- `session_handle(token)` stays `sha256(token)[:16]`, which equals `sessions.id[:16]`. Handles already in `audit_log` stay valid, and the Security page can derive a row's handle without the token.
- A migration (next free number) adds `authenticated_at` and **revokes every live session** (`UPDATE sessions SET revoked_at = now WHERE revoked_at IS NULL`). SQLite has no built-in sha256, so existing raw ids cannot be rehashed in SQL. Each user signs in again once, after the deploy.
- N-1 rollback (ADR-0071): the migration is expand-only (one nullable column plus an `UPDATE`). An older image would look up the raw cookie value against hashed ids, find nothing, and send users to login. That is acceptable, and the T-D53 CHANGELOG entry must flag it.

### 4. Session id rotation on privilege change

Login already issues a fresh session (ADR-0070 §2). A successful re-auth (§2) and a successful password change (ADR-0074) now also issue a new token for the **same** session. The server updates `sessions.id` to the new hash in place, keeping `created_at`, so the absolute cap (§1) cannot be reset by re-authenticating, and sets the new cookie. The old token stops working at once. Both flows are full-page form or ceremony submissions, so no concurrent HTMX requests race the swap.

### 5. Deferred (recorded, not in T-D53)

- **Periodic rotation**, e.g. daily. Concurrent HTMX swaps would race the cookie swap, so this needs a grace window where the previous token is still accepted. §1 and §4 already limit how long a stolen token stays valuable.
- **Binding sessions to user agent or IP.** User agents change with every browser update and mobile IPs change constantly, so a hard bind locks out real users. A soft "unrecognised device" flag would need a notification channel, and v3 has none.
- **New-sign-in notifications.** There is no email or push channel in v3. The Security sessions list (last seen, device, IP) remains the place to check.

## Consequences

### Positive

- A stolen cookie is worth at most 30 days and stops working at the next re-auth or password change. It cannot be turned into a passkey or password the attacker controls without the victim's credential.
- A leaked DB file, backup or Litestream replica no longer contains any usable session token.
- Admin actions on other users require a fresh credential, which limits the damage from a hijacked admin session.

### Negative

- Users re-login about once a month on each device.
- Sensitive actions need an extra passkey tap or password entry when the session's last authentication is older than 10 minutes.
- Every user is signed out once when the T-D53 migration runs.
- New surface: one page, three POST routes, one rate-limit scope, one challenge purpose, two settings.

## Alternatives considered

- **Short-lived access token + refresh token.** Rejected (see Context). It adds a second token in the same cookie jar and buys no extra revocation, because sessions are already server-side.
- **Shorter sliding lifetime and no absolute cap.** A stolen token still lives forever while in use, and honest users re-login more often. Rejected.
- **Step-up on every state-changing request.** Too much friction for budgeting edits that do not enable account takeover. Rejected.
- **Rehash existing sessions in a Python migration step.** It would avoid the one-time sign-out. Rejected: the migration runner only loads `NNNN_slug.sql` files (`db/migrate.py`), and one re-login is cheap.
