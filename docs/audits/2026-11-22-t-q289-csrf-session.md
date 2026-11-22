# T-Q289 frontend audit: session-bound CSRF token (2026-11-22)

Change: `static/csrf.js` adopts the `X-CSRF-Token` response header after an HTMX request (refreshes
`<meta name="csrf-token">` when the server re-binds the token on login, logout or session rotation); `?v=1` to
`?v=2` on the script tag in `base.html` and `auth/_layout.html`. No copy, class, layout or CSS change; no
arithmetic or literal added to any template.

## Sweep (frontend-visual-audit skill, Steps 2, 3, 3b)

Driver: the skill's diagnostics ported to Playwright-Python, run against a live uvicorn on a scratch SQLite
(temporary e2e test, removed afterwards). Logged in through the real password form. `data/budget.sqlite`
untouched. Full-page screenshots captured for every row.

Routes: `/today`, `/settings/security`, `/accounts`; viewports 1440, 1024, 375 (9 rows).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /settings/security | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /accounts | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |

Screenshots (`/tmp/fe289/<width>_<route>.png`): viewed `375_settings_security.png`: password form, passkeys and
sessions cards lay out normally, bottom bar and sign-out visible; nothing clipped.

## Step 3b (behaviour contract)

1. Swap targets: no `hx-target` touched.
2. Failing saves: a rejected token returns 403 and the existing global handler (`js/app-init.js`, ADR-0143) shows
   "The request was refused. Reload the page and try again."; unchanged.
3. No template arithmetic added (only the `?v=` query string changed).
4. to 5. Not applicable (no money rendering touched).
6. Listeners: the new `htmx:afterRequest` listener reads a header only; no `HX-Trigger` emitted or added.
   Meta tag present on every audited page. e2e change-password then sign-out (session rotation in the same tab)
   passes because the token is refreshed from the header.
7. Scratch data only.

Findings: none.
