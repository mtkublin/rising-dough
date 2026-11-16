# ADR-0075: Security controls live in Settings

- Status: Accepted
- Date: 2026-11-04
- Amends: [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) (nav placement), [ADR-0074](0074-password-change-policy-and-forced-rotation.md) (page placement), [ADR-0073](0073-user-admin-panel-guard-and-one-shot-password.md) (tab strip)

## Context

T-D02b and T-D18 added two links to the navigation rail ("Security", "Password") and two standalone pages. The product owner does not want account management in primary navigation; Settings already hosts tabbed configuration.

## Decision

1. The rail keeps only the signed-in email and the Sign out button. The mobile "Account & sign out" link becomes a "Sign out" button.
2. Settings gains a **Security** tab (`GET /settings/security`, every signed-in user, between Preferences and Users) with three sections in order: Password, Passkeys, Sessions. It reuses `static/js/passkeys.js` and the unchanged JSON endpoints `/auth/register/begin|finish`.
3. `GET /auth/sessions` and `GET /auth/register` answer `303` to `/settings/security#sessions` / `#passkeys`. All POST endpoints keep their URLs; their redirects (revoke, register finish `{redirect}`, password success) point into the Security tab.
4. `GET /settings/password` answers `303` to `/settings/security#password` for users who are not forced. For `must_change_password` users it remains the standalone rotation page (no Settings chrome), the middleware exempt list is unchanged (`/settings/password`, `/auth/logout`), and `next` is honoured after rotation. A forced user is redirected away from `/settings/security` like any other gated route.
5. One stylesheet, `settings-security.css` (renamed from `settings-password.css`), serves both the tab and the forced page. No inline scripts or styles (CSP, ADR-0036 / T-D07).

## Consequences

- Fewer primary-nav items; account controls are discoverable under Settings.
- Old bookmarks keep working via redirects. Rate limits, audit rows and CSRF behaviour are unchanged.

## Addendum: passkey registration failed in dev ("The passkey wasn't added")

Root cause: the WebAuthn relying party came from static defaults (`rp_id=localhost`, `origin=http://localhost:8000`). Two dev setups broke against them: (1) any port other than 8000 — the server rejected the attestation origin (`invalid_response`); (2) opening the app as `http://127.0.0.1:8000` — browsers refuse an IP literal as an RP ID, so the ceremony never reached the server. The failure reason was also not logged.

Decision: when `env=dev` and neither `BUDGET_WEBAUTHN_RP_ID` nor `BUDGET_WEBAUTHN_ORIGIN` is set, the RP ID and origin are derived from the request host (scheme + host:port). Explicit settings always win, and production/test never derive. When a dev server is reached by IP literal, `/auth/register/begin` and `/auth/login/begin` answer `400 {"error":"passkey_host_unsupported"}` and the UI says to open `http://localhost:<port>`; `just dev` prints that URL. Failed registrations log `passkey_register_failed` (reason, rp_id, origin) at warning level. `passkeys.js` reloads after a same-page redirect so the new passkey is listed. Covered by `tests/e2e/test_passkey_journey.py` (CDP virtual authenticator: register, sign out, sign in with the passkey). Real-device verification remains a human step.
