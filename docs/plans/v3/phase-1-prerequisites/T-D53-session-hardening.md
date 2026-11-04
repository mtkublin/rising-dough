# T-D53 — Session hardening (absolute cap, step-up re-auth, hashed ids)

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: no. T-D53a and T-D53b are sequential, and both touch `web/routers/auth.py` and `repositories/sessions.py`.
- **Depends on**: T-D02, T-D09, T-D14, T-D17, T-D18. Also T-D47 (ADR-0075 Security tab), only for the UI placement of the sessions list and the re-auth link.
- **Blocks**: T-D27 (first prod apply). Ship before real users get sessions, so the one-time sign-out costs nothing.
- **References**: [ADR-0076](../../../adr/0076-session-hardening-absolute-cap-step-up-hashed-ids.md) (amends ADR-0067 §2, ADR-0070 §2–§3)

## Context

ADR-0076 closes four gaps that make a stolen session cookie valuable: no absolute lifetime, no step-up for account-takeover actions, raw session ids at rest, and no id rotation on privilege change. Access/refresh tokens were considered and rejected (see ADR-0076 Context).

## T-D53a — Hashed ids + absolute cap + migration

1. **Migration** `migrations/NNNN_session_hardening.sql` (next free number) plus a `down/` script:
   - `ALTER TABLE sessions ADD COLUMN authenticated_at TIMESTAMP` (nullable).
   - `UPDATE sessions SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE revoked_at IS NULL`, so every existing raw-id session is retired.
2. **Settings** (`config.py`): `session_absolute_lifetime_days` (default 30, `ge=1, le=365`); `session_reauth_window_minutes` (default 10, `ge=1, le=60`); a model validator that rejects `session_absolute_lifetime_days < session_lifetime_days`. Document both in the env reference and the `.env.example` equivalents.
3. **Repository** `repositories/sessions.py`:
   - `create_session` returns `IssuedSession(session, token)`. It stores `sha256(token)` hex as `id` and sets `authenticated_at = created_at`.
   - `get_session` / `touch_session` / `revoke_session` take the **token** and hash it internally. No caller hashes by hand.
   - `touch_session` clamps `expires_at` to `created_at + absolute lifetime`.
   - `session_handle(token)` is unchanged (`sha256(token)[:16]`). Add `Session.handle` = `id[:16]` and assert in a test that the two agree.
   - `rotate_session_token(conn, token) -> IssuedSession`: new token, same row (`id` swapped in place), `created_at` preserved.
   - `mark_authenticated(conn, token, now)`.
   - `Session.authenticated_at` hydrates `NULL` as `created_at`.
4. **Web**: `web/auth_cookies.py` sets `Max-Age` from the clamped `expires_at`. `AuthRequiredMiddleware` passes the raw cookie token to the repository, and `request.state.session_id` stays the raw token (ADR-0070 §5).
5. **Security sessions list** shows the absolute expiry date per session.

## T-D53b — Step-up re-auth + rotation

1. **Dependency** `web/deps.require_recent_auth`, which uses `settings.session_reauth_window_minutes`. Stale requests get the responses from ADR-0076 §2 (HTMX 403 + `HX-Redirect`; JSON 403 + `redirect`; otherwise 303 to `/auth/reauth?next=`).
2. **Guard** these routes: `POST /auth/register/begin|finish`, `POST /auth/passkeys/{id}/revoke`, `POST /auth/sessions/{handle}/revoke` (only when the target is not the current session), and every `POST` in `web/routers/settings_users.py`.
3. **Re-auth routes** in `web/routers/auth.py`:
   - `GET /auth/reauth`: page with "Confirm with passkey" (shown only if the user has passkeys) and a current-password form.
   - `POST /auth/reauth/begin|finish`: an authentication ceremony with `allowCredentials` = the session user's credentials. `finish` rejects a credential owned by anyone else. The challenge cookie uses purpose `"reauth"`, bound to `user_id`.
   - `POST /auth/reauth`: current password.
   - Success sets `authenticated_at`, calls `rotate_session_token`, sets the new cookie, and redirects to the validated `next`.
4. **Password change** (`POST /settings/password` success): also `mark_authenticated` + `rotate_session_token`.
5. **Rate limit**: scope `reauth`, per user, 5 / min + 20 / hour, covering `POST /auth/reauth` and `POST /auth/reauth/finish`. Settings `BUDGET_RATE_LIMIT_REAUTH_PER_MINUTE` / `_PER_HOUR`. Throttled → 429 + `Retry-After`, generic error, audit row (ADR-0072).
6. **Audit**: `auth_event` rows `reauth` / `reauth_failed` (`method`, `reason`), with the session handle taken from `RequestCtx`.
7. **`passkeys.js`**: on `403 {"error":"reauth_required"}`, navigate to `redirect`.
8. **Template** `templates/auth/reauth.html`, styled with the existing auth/settings-security CSS. No inline scripts or styles (CSP).

## Acceptance criteria

- Unit (`tests/unit/repositories/test_sessions.py`):
  - The DB never contains the raw token (assert `id != token` and `id == sha256(token)`).
  - `touch_session` never extends past `created_at + absolute lifetime`, and the session is dead after it.
  - Rotation keeps `created_at`, the old token stops resolving, and the new token resolves.
  - `NULL authenticated_at` reads as `created_at`.
  - The settings validator rejects absolute < sliding.
- Migration test: a pre-migration DB with live sessions ends up with every session revoked and `authenticated_at` present.
- Integration (`tests/integration/web/test_auth_reauth.py`):
  - Each guarded route returns the stale response once the window has passed (time injected, no sleeps), in all three response shapes.
  - Passkey re-auth with another user's credential fails.
  - Password re-auth succeeds, rotates the cookie (the old cookie now gets a login redirect), and lands on `next`.
  - Revoking your own session needs no re-auth.
  - The rate limit fires at 429.
  - Both outcomes are audited.
- E2E: the CDP virtual-authenticator journey (as in `tests/e2e/test_passkey_journey.py`) adds a second passkey after a forced-stale window, through the re-auth page.
- Frontend visual audit (CLAUDE.md) on `/auth/reauth` and the Security tab at 1440 / 1024 / 375.
- The CHANGELOG entry flags the one-time sign-out and the N-1 rollback behaviour (ADR-0076 §3).
- `runbooks/user-admin.md` (T-D46) says that admin actions under `/settings/users` ask for re-auth after `session_reauth_window_minutes` and how to complete it. `runbooks/deploy.md` notes the one-time sign-out on the deploy that ships the migration.
- The T-D43 smoke journey (`tests/smoke/test_prod_smoke.py`) passes with re-auth enabled. Either keep its admin steps inside the re-auth window after login, or add a re-auth step that exercises `/auth/reauth`. The second is preferred because it covers the flow in production.

## Validation hook

```sh
just test tests/unit/repositories/test_sessions.py
just test tests/integration/web/test_auth_reauth.py
just ci
# scratch DB: just dev --db=/tmp/scratch.sqlite
#   sign in → wait past BUDGET_SESSION_REAUTH_WINDOW_MINUTES=1 → add passkey → re-auth page → passkey added
#   sqlite3 /tmp/scratch.sqlite "select id from sessions" shows 64-hex hashes, never the cookie value
```
