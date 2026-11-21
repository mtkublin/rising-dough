# Frontend audit: T-Q256 card utilisation and passkey JS

Change: T-Q256 (Q-070, Q-071). `web/accounts_view.py` `credit_utilisation(account, balance)` replaces the
utilisation arithmetic in `partials/accounts/_card.html`, `_row.html`, `accounts/index.html` and the router's
`_uses_available`; `_override_form.html` takes `form_month`/`form_year` from the router (no `10` default);
`'PLN'` template fallbacks replaced by the `base_ccy` global (planned `_row` drops `default('PLN')`); new
`static/csrf.js` (`window.budgetCsrf.token()`) shared by `htmx-csrf.js` and `js/passkeys.js`; `passkeys.js`
extracts `runAssertion`, renames `resp403` to `isReauthRequired`, logs `err.name` to `console.debug`.

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q256.sqlite` (never `data/budget.sqlite`), logged in through the real form.

## Routes and diagnostics

Routes: `/auth/login` (anonymous), `/accounts`, `/settings/security` (passkeys page), `/today`, each at
1440, 1024 and 375 (12 runs, all HTTP 200).

| Diagnostic | Result |
|---|---|
| horizontalScroll | false in all 12 runs |
| overflowingElements | 0 in all 12 runs |
| duplicateIds | 0 in all 12 runs |
| requestFailures | 0 in all 12 runs |
| consoleErrors | 0 in 11 runs; 1 at 1440 `/auth/login`, see below |

The one console error is the browser's "Failed to load resource: 400" line from the deliberate passkey button
click in the audit (the dev server on `127.0.0.1` answers `/auth/login/begin` with 400 because passkeys need a
hostname). It is not a script error; the page showed the generic sign-in error and `console.debug` printed
`passkey ceremony failed: Error` (error class only, no message), proving `csrf.js` + `passkeys.js` load and run.

## Step 3b

1. Swap targets: no `hx-target`/`hx-swap` touched.
2. Failing saves: no form changed behaviour; passkey failure still shows the visible status message.
3. No arithmetic in touched templates: utilisation, bar width and over-limit amount are view-model fields;
   13 stale `template_logic` entries and 1 `thin_router` count deleted, none added.
4. Money formatting: through `money` / `money_num(currency)` (unchanged).
5. Rendered equals service: `/accounts` card shows `Limit 14,977.37 - Available 12,521.63 - Used 16%` on the
   scratch DB; integration test `test_accounts_index_renders_service_utilisation` asserts the exact values.
6. `window.budgetCsrf` is an object on `/auth/login` and `/accounts`; token length 43.
7. Scratch data only: yes.

Screenshots: `/tmp/fe-audit-tq256/{desktop,tablet,mobile}__*.png`.
