# ADR-0076: Retire legacy home page; Today is the landing page

- Status: Accepted
- Date: 2026-11-04
- Amends: [ADR-0051](0051-v2-information-architecture-rising-dough.md) (retires the `/` shim), [ADR-0023](0023-ux-redesign-information-architecture.md) (Overview `/`), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) §4 (`next` fallback)

## Context

ADR-0051 made `/today` the canonical landing surface but kept the v1 Overview rendering at `/` "for bookmarks" until Phase 7 cleanup. The duplicate surface drifts from Today and `/overview/upcoming` keeps a second upcoming-list code path alive.

## Decision

1. There is no home/overview page. `GET /` (and `HEAD /`) answer `303` to `/today`. Anonymous visitors hit the auth middleware first and are sent to `/auth/login?next=%2Ftoday`.
2. One constant, `DEFAULT_LANDING = "/today"` (`web/auth_cookies.py`), is the fallback for `safe_next`, the login/passkey/rotation form defaults, and the "no destination" cases in the auth and password-rotation flows. Logout still lands on `/auth/login`.
3. The legacy home router, `templates/home/**` and the `/overview/upcoming` fragment are removed. The data helpers Today shared with the home router move to `web/today_data.py`. Brand/logo and the error-page "back" link point at `/today`.
4. No data, schema or API changes.

## Consequences

- One landing surface; bookmarks to `/` keep working via the redirect.
- `g o` / palette "Go to Overview" target `/today`.
