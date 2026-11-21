# ADR-0033: v3 Authentication — Single-User Passkey (WebAuthn) + Fallback Password

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28)
- **Related**: ADR-0005 (single user, no auth, user_id scaffolded), ADR-0032 (v3 remote deployment)
- **Amends**: ADR-0005. The server now authenticates every request; the single `user_id = 1` scaffold becomes the identity attached to each session.

## Context

ADR-0032 exposes Rising Dough on the public internet. Public exposure with zero auth is a non-starter for an app holding financial history. The constraint set is specific:

- Exactly one user ever.
- The user is technical and has access to a password manager and modern browsers (Chrome, Safari, Firefox) with WebAuthn support on at least one device.
- No support burden, no multi-user flows, no "forgot password" email loop. The user is the admin.
- Login friction should be minimal on the user's own devices.

Options evaluated:

1. **Passkey (WebAuthn, platform authenticator)** — biometric unlock on the user's devices, no password typed daily, no SMS/email dance. Open standard, browser-native.
2. **Long random password only** — simplest to implement but typed on every login; weakest against phishing (passkeys are phishing-resistant by design).
3. **Basic HTTP auth** — simple, but credentials leak into browser history, no logout, no session management, and no second factor.
4. **Tailscale / VPN only** — zero public exposure. Rejected because the user explicitly wants internet accessibility from any device without a VPN client installed.
5. **OIDC with GitHub/Google** — introduces a third-party dependency and a per-login external hop for a one-user app.

## Decision

Authenticate every non-health, non-ACME request with a server-signed session cookie. Session issuance paths:

### 1. Primary: Passkey (WebAuthn, platform authenticator)

- Library: `py_webauthn` (official FIDO Alliance Python library, maintained, no JS framework required).
- Credential storage: a new `webauthn_credentials` table in SQLite (`id`, `user_id`, `credential_id` BLOB UNIQUE, `public_key` BLOB, `sign_count` INTEGER, `transports` TEXT, `created_at`, `last_used_at`, `label` TEXT, soft-delete + audit per ADR-0019).
- Registration flow: `/auth/register` — gated by the fallback password (section 2). The user can register multiple passkeys (one per device) and name them (`iPhone 15`, `MacBook Air`, hardware key).
- Login flow: `/auth/login` — WebAuthn ceremony → session cookie.
- Relying Party ID: the deployed hostname (e.g. `budget.example.com`).
- User verification: `required` (biometric or PIN).
- Replay protection: standard `sign_count` monotonic check; on anomaly, the credential is auto-revoked and the fallback-password path is required to re-register.

### 2. Fallback: long random password (break-glass only)

- A single bcrypt-hashed password stored in a new `auth_password` table (`id`, `user_id`, `bcrypt_hash`, `updated_at`). One row only.
- The plaintext is generated at provisioning time by Terraform (via `random_password` resource with 32-char alphanumeric + symbols) and surfaced *once* in `terraform output -raw admin_fallback_password` for the user to paste into their password manager. Never logged, never checked in.
- Login via `/auth/fallback-login` — rate-limited to **3 attempts per 15 minutes per IP** (slowapi) + `fail2ban` jail reading Caddy access logs.
- Intended use: initial passkey registration + emergency recovery if every passkey is lost.
- Rotation: `just rotate-fallback-password` emits a new password via Terraform; old hash is overwritten in a single transaction.

### 3. Session

- Cookie: `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, no `Domain` attribute (binds to the exact origin).
- Value: `itsdangerous`-signed token wrapping `{user_id, session_id, issued_at, expires_at}`.
- Session store: a new `sessions` table in SQLite (`id`, `user_id`, `issued_at`, `expires_at`, `last_seen_at`, `user_agent`, `ip`, `revoked_at`).
- Lifetime: **sliding, 7 days**, refreshed on each authenticated request. Idle timeout: 7 days.
- Revocation: `POST /auth/logout` sets `revoked_at = now()` on the current session; `POST /auth/sessions/<id>/revoke` revokes any session by id (useful from a trusted device).
- A `/auth/sessions` view lists active sessions with device/last-seen metadata; the user can revoke individually.

### 4. CSRF protection

- Every state-changing request (POST/PUT/PATCH/DELETE and HTMX-driven POSTs) requires an `X-CSRF-Token` header matching a per-session token stored in a signed cookie.
- Set once on login (`__Host-csrf`), read by a small HTMX extension that injects it as a request header.
- GETs are safe (templates are read-only).

### 5. Middleware shape

Order (outermost first):
1. `TrustedHostMiddleware` — only accept requests whose `Host` header matches the deployed hostname.
2. `SecurityHeadersMiddleware` — enforces the CSP / HSTS / nonce injection.
3. `SessionMiddleware` — parses the signed cookie, hydrates `request.state.user`.
4. `AuthRequiredMiddleware` — redirects unauth to `/auth/login` for HTML; returns `401 { "error": "unauthorized" }` for `Accept: application/json` or `HX-Request: true`.
5. `CSRFMiddleware` — validates the token for non-GET methods.
6. The app routers.

Public routes exempt from `AuthRequiredMiddleware`: `/health`, `/ready`, `/auth/login`, `/auth/login/finish`, `/auth/fallback-login`, static assets, `/.well-known/*`.

### 6. Audit

- Every login success/failure, logout, session revocation, passkey registration, passkey removal, and fallback-password rotation writes an `audit_log` entry per ADR-0019.
- The audit entry includes IP, user-agent, outcome, and the credential label if applicable.

## Consequences

### Positive

- Daily use is a biometric tap. No password typed.
- Passkeys are phishing-resistant by design. Credential-stuffing attacks against the fallback password are rate-limited and jail-triggering.
- No external auth dependency. The whole flow lives inside the app and SQLite.
- The `user_id = 1` scaffold from ADR-0005 is preserved; schema does not need a user management panel.

### Negative

- First-time setup requires the user to open the fallback-password route from the Terraform output to register the first passkey. Documented in the runbook.
- If every passkey AND the fallback password are lost, recovery requires `terraform apply` to rotate the fallback password, which requires access to the Scaleway account. There is no email-reset path by design.
- Adds four tables (`webauthn_credentials`, `auth_password`, `sessions`, `auth_rate_limit`) and seven routes to the surface area. Material code additions covered in Phase 1 tasks.

### Follow-ups

- A later ADR may add a hardware security key as a required second credential alongside the platform passkey, if the threat model shifts. Not required for v3.

## Alternatives Considered

- **Basic HTTP auth** — rejected (no logout, no second factor, credentials in browser history).
- **Tailscale / VPN only** — rejected (user explicitly wants internet access without a VPN client).
- **OIDC via GitHub** — rejected (external hop every login, extra service to monitor, overkill for one user).
- **Password only (no passkey)** — rejected (typed on every login, phishable, no device trust).
