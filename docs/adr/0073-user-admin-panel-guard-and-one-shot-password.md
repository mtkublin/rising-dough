# ADR-0073: User Admin Panel — 404 Guard, One-Shot Password Delivery, Invariant Errors, Audit Attribution

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §4 (routes) and §5 (audit attribution)
- **Related**: T-D17, [ADR-0074](0074-password-change-policy-and-forced-rotation.md) §3 (forced-rotation gate, ordered outside this guard), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) §6 (middleware order), [ADR-0019](0019-soft-delete-and-audit-log.md) (audit operations), [ADR-0068](0068-user-scoping-static-check-policy.md) (user-scoping check)

## Context

ADR-0061 §4 lists the `/settings/users` routes and says non-admins get a 404 from an `AdminRequiredMiddleware`. It leaves open:

1. Where the guard sits in the middleware stack and what the 404 body looks like.
2. How the one-shot password reaches the browser without being cached, logged or stored.
3. Which status the last-admin refusal returns. The T-D17 task file says `422`; the user-admin runbook says `409`.
4. Whether an admin may remove their own account. The task file says never; the runbook says yes if another admin exists.
5. How `audit_log.actor_user_id` (migration 0012) gets written. `write_audit` only wrote the request-context columns from migration 0013.
6. What the audit `operation` is for a password reset. The runbook queried `operation=reset_password`, but `audit_log.operation` has a `CHECK (operation IN ('create','update','delete','undelete'))`.

## Decision

### 1. Guard: `AdminRequiredMiddleware`, between AuthRequired and CSRF

`web/middleware/admin.py` gates the `/settings/users` path and everything under `/settings/users/`. If `request.state.user` is missing or not an admin, it answers with the app's normal 404 (`errors.handle_not_found`: the full 404 page, or the flash fragment for HTMX). The body is the same one any unknown path gets, so nothing about the admin surface leaks.

It is registered right after `CSRFMiddleware` in `create_app`, inside T-D18's `MustChangePasswordMiddleware` (ADR-0074 §3). The order is now RequestId → SecurityHeaders → AuthRequired → MustChangePassword → **AdminRequired** → CSRF → routers. This has three effects:

- anonymous requests never reach the guard; AuthRequired sends them to login first (ADR-0070 §4);
- a non-admin POST without a CSRF token still gets a 404, not a 403 that would show the route exists;
- a user flagged `must_change_password` gets the rotation redirect on `/settings/users*` first, admin or not. MustChangePassword answers every non-exempt path that way, unknown paths included. If the admin guard ran first, a flagged non-admin would get 404 here but a redirect on `/no-such-page`, and that difference would reveal the admin surface. With the guard inside, both answers are the same while the flag is set. After rotating, a non-admin gets the standard 404 and an admin gets the panel.

The router adds a `current_admin` dependency as a second layer of defence. It raises `HTTPException(404)` if the router is ever mounted without the middleware.

### 2. One-shot password: HTMX fragment, `no-store`, no persistence

- The password is `secrets.token_urlsafe(16)` (ADR-0061 §8). It is hashed before the write transaction opens, so bcrypt does not hold the SQLite write lock.
- Only the response body carries the plaintext: a toast fragment swapped into `#user-feedback`, holding `<pre class="selectable">` and a copy button. The response sets `Cache-Control: no-store`. The password is never put in an `HX-Trigger` header, a URL, a log line or an audit row.
- Copy-to-clipboard and toast dismissal live in `static/js/users-admin.js`. There is no inline script, as CSP nonce rules require (ADR-0036). The toast stays until it is dismissed; it does not time out like `#toast-root` toasts do.
- Without JS, `POST /settings/users` and `POST /settings/users/{id}/reset-password` re-render the list page with the toast inline. They do not redirect, because a redirect would drop the password.

### 3. Invariant errors: `409 Conflict`; input errors: `422`

- Deleting or demoting the last live admin returns **409**. So does removing your own account. The service raises `UserConflict`.
- An invalid or duplicate email (case-insensitive, live users only) returns **422** (`UserInputError`), and the form is re-rendered with the field error.
- The service raises `UserNotFound` for a missing target. The router maps all three to responses itself, using the same `errors/404.html`, `errors/409.html` and flash templates as `web.errors`. These are plain exception classes in `services/users.py`, not the frozen-dataclass `domain.errors` types. Python's `contextmanager` (used by `transaction()` and FastAPI's generator dependencies such as `get_db`) sets `__traceback__` on any exception that passes through it, and a frozen dataclass refuses that assignment, so a `domain.errors` exception that crosses that boundary turns into a `FrozenInstanceError` 500.
- A missing or soft-deleted target user returns **404**.
- For HTMX requests from the panel, `users-admin.js` lets 409 responses swap. The response carries `HX-Reswap: none`, so only the out-of-band flash renders.

This replaces the `422` in the T-D17 task file. The runbook already said `409`.

### 4. No self-removal

An admin cannot soft-delete their own account, even when other admins exist. Another admin has to do it. This keeps the acting admin from revoking their own session in the middle of a request, and it makes "lock myself out" impossible from the UI. Self-demotion is still allowed when another live admin exists. The last-admin rule covers the lockout case there.

### 5. Audit attribution

`repositories._shared.write_audit` takes a new keyword `actor_user_id: int | None = None`, written to `audit_log.actor_user_id`. Existing callers do not change; the column stays NULL for them. Every admin mutation in `repositories/users.py` passes the admin's id. The request-context columns (`user_id`, `ip`, `session_id`, `user_agent`) are still filled from `RequestCtx`. For admin actions, `user_id == actor_user_id`, and `entity_id` is the target user.

The `Transit` / `Reconciliation` category rows seeded for a new user also carry `actor_user_id`.

### 6. Audit operations

| Action | `operation` | `prev_json` | `new_json` |
|---|---|---|---|
| Add user | `create` | — | redacted user (`password_set: true`) |
| Edit user | `update` | redacted user | redacted user |
| Reset password | `update` | redacted user | redacted user + `"action": "reset_password"`, `"sessions_revoked": n` |
| Remove user | `delete` | redacted user | — (ADR-0019 shape rule) |

The redacted user shape is the one T-D19 already uses (`password_set` instead of any hash). No plaintext or hash is ever written. To find resets, query `operation = 'update' AND json_extract(new_json, '$.action') = 'reset_password'`.

### 7. Listing users and the user-scoping check

`users.list_live` reads the `users` table, which is not user-owned (ADR-0068). The "last seen" column uses a correlated subquery on `sessions` keyed by `s.user_id = u.id`. It is roster metadata, not user data, and it passes the static check as written, so no `SQL_ALLOWLIST` entry is needed.

## Consequences

- Admin surfaces get one 404 code path, so they cannot be fingerprinted by status or body.
- The task file, the runbook and the code now agree on the error contract: 409 for invariants, 422 for input.
- `audit_log.actor_user_id` gets written for the first time. Forensic queries can filter on it directly.
- A lost toast cannot be recovered. The admin must reset the password again (runbook troubleshooting).

## Alternatives considered

- **Router dependency only (no middleware).** Simpler, but CSRF runs before routing, so a non-admin POST without a token would get a 403 and reveal the route. Rejected; the dependency is kept only as a second layer.
- **PRG redirect carrying the password in a signed flash cookie.** It would put the plaintext into a cookie and the browser's cookie store. Rejected.
- **422 for invariants (task-file wording).** 422 means the input was malformed, but the input here is fine; the roster's current state is what blocks the action. 409 is the accurate code.
