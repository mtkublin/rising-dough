# ADR-0074: Password Change — Policy, Audit Shape, and Forced-Rotation Responses

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §4 (`/settings/password`, `must_change_password` redirect); the T-D18 task file's "new == old allowed" note
- **Related**: T-D18, [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md) (sessions), [ADR-0069](0069-admin-bootstrap-env-policy-and-operator-cli.md) (`update_credentials`), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) (middleware order), T-D09 (rate limiting)

## Context

ADR-0061 §4 defines `GET/POST /settings/password` and says the `must_change_password` flag forces a redirect there "before any other route is served". It does not settle:

1. The password policy: length limits, and whether the new password may equal the current one.
2. How a failed verify is audited. The T-D18 task file asks for `operation='update_failed'`, but `audit_log.operation` has a `CHECK (operation IN ('create','update','delete','undelete'))` constraint (migration 0002), and T-D18 adds no migration.
3. What the forced redirect looks like for HTMX and JSON clients, which cannot follow a 302 to an HTML form.
4. Which paths stay reachable while the flag is set.

## Decision

### 1. Password policy (server-side only)

- **Minimum 12 characters** (counted as Unicode code points; whitespace is kept as typed).
- **Maximum 72 UTF-8 bytes.** bcrypt ignores everything after byte 72, and `services._passwords.hash_password` raises `ValueError` past it. The form rejects the password with a clear message so we never silently truncate.
- **New must differ from current.** This only needs the current plaintext, which the form already supplies, so no password-history table is required. It stops a forced rotation (admin-issued or bootstrap password) from being "completed" by re-entering the same secret. This replaces the T-D18 task file's "new == old allowed" note.
- **Confirm must match new.** No composition rules or strength meter.

All failures are reported together, per field, and re-render the form with status `422`.

### 2. Change flow and audit shape

`services/password_change.change_own_password` does:

1. Validate the policy (pure).
2. Verify the current password with bcrypt **outside** any transaction (bcrypt at cost 12 takes ~250 ms; holding the SQLite write lock that long is not acceptable). Hashing the new password also happens outside.
3. In **one** transaction: re-read the user and confirm the hash is unchanged since step 2 (otherwise fail as a stale attempt), call `repositories.users.update_credentials(password_hash=…, must_change_password=False)` (writes the `users`/`update` audit row with `password_changed: true`, no hash), revoke every other session of the user with `sessions.revoke_all_user_sessions(except_session_id=<current>)`, and, when any were revoked, write one `session`/`delete` audit row `{event: "password_change_revoke_others", count}`.

A failed verify writes one row `entity_type='auth_event'`, `entity_id=<user_id>`, `operation='create'`, `new_json={event: "password_change_failed", reason: "bad_current_password" | "no_password"}`. This mirrors the existing `login_failed` rows (ADR-0067 §4) and fits the existing CHECK constraint. Every row carries IP, user-agent, user id and session handle from `RequestCtx`. Passwords and hashes never reach `audit_log` or logs.

Validation-only failures (mismatch, too short) with a correct current password write no audit row: nothing was attempted against the credential.

### 3. Forced rotation: `MustChangePasswordMiddleware`

Registered directly inside `AuthRequiredMiddleware` (between it and CSRF, as ADR-0070 §6 anticipated). When `request.state.user.must_change_password` is true and the path is not exempt:

| Client | Response |
|---|---|
| HTML | `302 Location: /settings/password?next=<original path+query>` |
| HTMX (`HX-Request: true`) | `403` JSON `{"error": "password_change_required", "location": "/settings/password"}` + `HX-Redirect: /settings/password?next=<HX-Current-URL path>` |
| JSON (`Accept: application/json` without `text/html`) | `403` JSON `{"error": "password_change_required", "location": "/settings/password"}` |

`403` (not `401`) because the caller *is* authenticated; it is forbidden from everything else until it rotates. `next` goes through `safe_next` (same-site relative paths only).

Exempt while the flag is set: `/settings/password`, `/auth/logout`, `/static/*`, `/health`, `/ready`, `/healthz`. Anonymous requests are untouched (the auth layer already handled them).

### 4. Rate limiting is deferred to T-D09

The T-D18 task file asks for a shared rate-limit counter with `/auth/login`. No rate limiter exists yet (`slowapi` is not a dependency); T-D09 owns it. The `password_change_failed` audit rows give T-D09 a per-user signal to count against.

## Consequences

- Dev bootstrap password `admin` (ADR-0069) cannot be reused: the first rotation must pick a 12+ character password.
- A user rotating their password keeps the current device signed in and is signed out everywhere else.
- HTMX/JSON clients get a machine-readable `password_change_required` code instead of silently-failing swaps.
