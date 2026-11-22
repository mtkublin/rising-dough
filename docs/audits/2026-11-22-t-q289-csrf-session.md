# T-Q289 frontend audit: session-bound CSRF token (2026-11-22)

Change: `static/csrf.js` adopts the `X-CSRF-Token` response header after an HTMX request (refreshes
`<meta name="csrf-token">` when the server re-binds the token on login, logout or session rotation); `?v=1` to
`?v=2` on the script tag in `base.html` and `auth/_layout.html`. No copy, class, layout or CSS change; no
arithmetic or literal added to any template.

## Sweep (frontend-visual-audit skill: Steps 2, 3, 3b)

Driver: the skill's audit script (Python port of `audit-frontend.js`, same DIAGNOSTIC and per-route/viewport
loop, plus a real password login) against a live uvicorn (`env=dev`, plain HTTP) on a scratch SQLite (copy of
`data/demo.sqlite`, migrated, scratch password set via `just set-password --db=`). `data/budget.sqlite`
untouched. Signed in once through the real login form; the session was reused for the signed-in routes.
Full-page screenshots in `/tmp/fe-audit-289/`.

Routes: `/auth/login` (anonymous), `/today`, `/settings/security`, `/accounts`; viewports 1440 (desktop),
1024 (tablet), 375 (mobile): 12 rows.

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /auth/login | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /today | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /settings/security | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /accounts | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |

Also 0 broken images on every row; `<meta name="csrf-token">` present with a non-empty value on every row.

Screenshots viewed: `mobile__auth_login.png` (login form, passkey button, no clipping at 375),
`tablet__today.png` (shell, hero, net worth and upcoming list lay out; no overflow), `stale_token_flash.png`
(below). Findings: none from this change. The demo data's narrow description column in the Today upcoming list
is pre-existing and unrelated.

## Step 3b (behaviour contract)

1. Swap targets: every `hx-target` on `/settings/security` resolves to exactly one element (`this` and
   `#modal-root`: 1 each); none added or changed.
2. Failing saves are visible. The password form was forced (via `page.route`) to return 404, 409 and 500; each
   showed a toast: "That item was not found. It may have been removed.", "That item changed in the meantime.
   Reload and try again.", "Something went wrong on our side. Try again." The new case from this change: a tab
   with a stale token (meta token overwritten with an unbound value, then Change password) is answered with the
   real 403 `invalid_csrf` and shows "The request was refused. Reload the page and try again." (existing global
   handler, ADR-0143; screenshot `stale_token_flash.png`).
3. No arithmetic, `float` or literals added to any template (only the `?v=` query string changed in
   `base.html` and `auth/_layout.html`).
4. and 5. Not applicable: no money rendering touched.
6. Ids and listeners: after a real HTMX swap (wrong current password) there are 0 duplicate ids and the meta
   token is still present. The new `htmx:afterRequest` listener reads a response header only; no `HX-Trigger`
   emitted or added. The e2e suite covers the rotation path (change password then sign out in the same tab).
7. Scratch data only (`/tmp/scratch289.sqlite`, removed afterwards).
