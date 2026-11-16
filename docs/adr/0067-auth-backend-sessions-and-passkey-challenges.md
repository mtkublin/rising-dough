# ADR-0067: Auth Backend — Opaque Server-Side Sessions, Caller-Held Passkey Challenges

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0033](0033-v3-auth-single-user-passkey.md) §1, §3, §6 (as already amended by [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md))
- **Related**: T-D02a (backend core), T-D02b (web layer), T-D09 (rate limit), T-D14 (audit request ctx)

## Context

T-D02 is split in two. T-D02a lands the backend (migration `0014_v2_auth.sql`, password hashing, sessions + WebAuthn repositories, `services/auth.py`); T-D02b wires middleware, routes and templates. Several decisions are not settled by ADR-0033/0061 and have to be fixed before T-D02b can consume the API:

1. Where the WebAuthn challenge lives between `begin` and `finish`.
2. What the session cookie carries (ADR-0033 §3 describes an `itsdangerous` wrapper around `{user_id, session_id, ...}`).
3. How sign-count anomalies are detected without letting an attacker revoke a credential with forged data.
4. What audit rows look like for events that do not map to a row mutation (failed logins), and whether raw session ids belong in `audit_log`.
5. The py_webauthn 3.x line requires `cbor2>=6` and `cryptography>=49`, which publish no macOS x86_64 wheels. The dev interpreter is x86_64.

## Decision

### 1. Passkey challenges are returned to the caller; the service stays stateless

`register_passkey_begin` and `authenticate_passkey_begin` return a frozen `PasskeyChallenge(options_json, challenge)`. The service does **not** persist the challenge. The web layer (T-D02b) stores `challenge` and passes it back to the matching `*_finish` call. The recommended carrier is a short-lived (≤ 5 min), `HttpOnly`, `SameSite=Strict` cookie signed with `itsdangerous` using `settings.cookie_secret`. It is cleared after `finish` whether `finish` succeeds or fails. Rationale: no extra table, no cleanup job, and `services/auth.py` stays a module of pure-ish functions over `conn`.

Relying-party identity comes from three new settings: `webauthn_rp_id` (default `localhost`), `webauthn_rp_name` (default `Rising Dough`), `webauthn_origin` (default `http://localhost:8000`). Production must set them to the deployed hostname / `https://` origin. Services take a `RelyingParty` value object (`relying_party_from_settings(settings)`) rather than reading globals.

Passkey login is **usernameless** (discoverable credentials, empty `allowCredentials`). The credential's `rawId` identifies the stored credential, and through it the user. Registration sets `residentKey=required` and `userVerification=required`, and excludes credentials the user has already registered.

### 2. Session cookie value = opaque random id = `sessions.id`

The session id is `secrets.token_urlsafe(32)` (256 bits), stored as `sessions.id TEXT PRIMARY KEY`, and used verbatim as the cookie value. There is no `itsdangerous` wrapper: the value is unguessable, and server-side lookup (revocation, expiry, user liveness) is authoritative anyway. Lifetime is **sliding** at `settings.session_lifetime_days` (default 14, which supersedes ADR-0033's 7). `touch_session` pushes `expires_at` forward and updates `last_seen_at`. `get_session` returns `None` when the session is revoked, expired, or belongs to a soft-deleted user.

### 3. Sign-count replay detection after signature verification

`authenticate_passkey_finish` calls `verify_authentication_response` with `credential_current_sign_count=0`, which disables the library's pre-signature check. It then compares `new_sign_count` with the stored count itself. A regression (`(new > 0 or stored > 0) and new <= stored`) on a response with a **valid signature** means the authenticator was cloned. The credential is soft-deleted (auto-revoked, audited) and login fails. Checking after signature verification stops an attacker from revoking a victim's passkey by sending forged authenticator data.

### 4. Audit shape for auth events

Every auth event writes `audit_log` via `write_audit(..., request_ctx=...)` (ADR-0019, T-D14). The `operation` CHECK only allows row verbs, so:

| Event | `entity_type` | `entity_id` | `operation` | payload |
|---|---|---|---|---|
| login success (password / passkey) | `session` | user id | `create` | `new={event, method, session, expires_at}` |
| login failure | `auth_event` | user id, or `0` when the email is unknown | `create` | `new={event:"login_failed", method, reason, email?}` |
| logout / session revoke | `session` | user id | `delete` | `prev={event, session}` |
| passkey registered | `webauthn_credential` | credential row id | `create` | sanitized view (no public key) |
| passkey revoked (manual or sign-count) | `webauthn_credential` | credential row id | `delete` | sanitized view + reason |

Raw session ids are bearer secrets, so they never go into `audit_log`. Payloads and the `audit_log.session_id` column carry a **session handle**: the first 16 hex chars of `sha256(session_id)` (`sessions.session_handle`). T-D02b should populate `RequestCtx.session_id` with the handle, not the cookie value.

### 5. Dependency pin

Runtime deps add `bcrypt>=4.2` and `webauthn>=2.7,<3`. `[tool.uv] constraint-dependencies` caps `cbor2<6` and `cryptography<49` so the lock resolves to versions with macOS x86_64 wheels. Linux images are unaffected. Revisit when upstream ships those wheels.

### 6. Schema notes

`webauthn_credentials` adds `last_used_at` and `deleted_at` (soft delete per ADR-0019) on top of the column list in the T-D02 handoff. `auth_rate_limit(id, key, bucket_start, count)` gets a unique `(key, bucket_start)` index. It ships empty until T-D09 uses it.

## Consequences

- T-D02b owns challenge transport (signed cookie) and must clear it after use. A stolen challenge cookie is useless without the authenticator's private key.
- A DB file leak exposes live session ids, because they are stored raw. This is accepted: that same leak already exposes all financial data, and sessions are revocable in bulk via `revoke_all_user_sessions`.
- bcrypt rejects passwords over 72 bytes. `hash_password` raises `ValueError` and `verify_password` returns `False`, with no silent truncation.

## Alternatives considered

- **Server-side challenge table**: needs TTL cleanup and couples the service to storage. Rejected for v3's ≤ 10 users.
- **`itsdangerous`-wrapped session payload**: adds nothing over a 256-bit random id with a server-side lookup. Rejected.
- **Pre-signature sign-count check (library default)**: lets an attacker revoke credentials with forged data. Rejected.
