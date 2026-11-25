# Frontend visual audit: T-UR21 first-run setup page

Task: T-UR21, branch wi/ui/sourdough/UR21. ADR-0027, ADR-0107, ADR-0134 section 9, ADR-0148, ADR-0150.
Method: frontend-visual-audit probe (Playwright, chromium) against a scratch server: a freshly migrated temp SQLite with zero users, `BUDGET_ENV=test`,
a configured `BUDGET_PLANNER_SETUP_TOKEN_HASH`; heavy lock /tmp/ui-redesign-heavy.lock taken and released around the run. data/budget.sqlite not touched.

## Routes and states

`/setup?token=...` in two states: open (empty form) and after a failed save (mismatched confirmation, server 422, inline `▲` error under the field).
Light and dark, each at 1440, 1024 and 375: 12 diagnostic rows. The e2e `tests/e2e/test_setup_page.py` also walks mismatch, fix, create, landing on
/today, and the redirect to sign in once setup is closed; the 404 without a token.

## Diagnostics

| State | horizontalScroll | overflowingElements | duplicateIds | requestFailures | consoleErrors |
|---|---|---|---|---|---|
| open, all widths, both themes | 0 | 0 | 0 | 0 | 0 |
| mismatch (422), all widths, both themes | 0 | 0 | 0 | 0 | 0 (1 expected: the browser's "Failed to load resource ... 422" line for the deliberate 422) |

The error is visible in every row (`#setup-confirm-error` visible, `aria-invalid` and `aria-describedby` set on the confirm field).

## Comparison

No handoff board exists for setup (derived.md row "First-run setup"). Compared by eye against `pages/auth/force-password` and `login` at 1440 and 375:
bake column and headline, title, lede, field labels, hint and `▲` error style, primary pill button match in structure, spacing and type. Phone: the bake
header collapses above the form like login.

## Findings

None blocking. The tablet and phone passes look like login. The 422 console line is expected behaviour.

## Step 3b

- Template pages/auth/setup.html: no `style=`, `{% set`, `float`, `/ 100`, `* 100`; messages come from `services.setup` and `services.users` (invalid
  email, under 12 characters, mismatch); the token and the name and email are echoed, the password fields are never refilled.
- Every failing save shows a visible error: field errors inline (422), throttle as the alert (429), wrong token a bare 404 by design (no oracle).

## Independent audit (visual-auditor, head 966e6dae)

Run by the visual-auditor role with the frontend-visual-audit skill method (Playwright chromium), separate from the implementer's probe above. Two scratch servers
(migrated temp SQLite, `BUDGET_ENV=test`, token hash configured, one with `BUDGET_RATE_LIMIT_LOGIN_IP_PER_HOUR=3` to reach the 429). Heavy lock
/tmp/ui-redesign-heavy.lock taken and released. data/budget.sqlite not touched. Screenshots (all viewed in part, listed below) are in
/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur21/out/ (not committed).

### Routes x viewports x themes (light and dark)

Routes: `/setup?token=<valid>` (open, 422 mismatch, 422 weak password, 429 rate limited), `/setup?token=wrong` (404), success landing `/today`.
Each state at 1440, 1024 and 375, light and dark: 36 rows, plus the success landing at 1440.

| State | Status | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| open (6 rows) | 200 | 0 | 0 | 0 | 0 | 0 |
| 404 wrong token (6 rows) | 404 | 0 | 0 | 0 | 0 (+1 expected browser 404 line) | 0 |
| 422 mismatch (6 rows) | 422 | 0 | 0 | 0 | 0 (+1 expected 422 line) | 0 |
| 422 weak password, 5 chars (6 rows) | 422 | 0 | 0 | 0 | 0 (+1 expected 422 line) | 0 |
| 429 (3 attempts per hour limit; 6 rows) | 429 | 0 | 0 | 0 | 0 (+ expected 4xx lines) | 0 |
| success lands on /today (1440 light) | 200 | 0 | 0 | 0 | 0 | 0 |

No broken images. Only the browser's own "Failed to load resource ... 4xx" lines for deliberate 4xx responses were excluded; no page errors or JS errors.

### Behaviour checked

- Valid token: form with name, email, password, confirm; token in hidden `#setup-token`; CSRF hidden field present.
- Wrong or missing token while open: 404 (FastAPI JSON `{"detail":"Not Found"}`, no form, no oracle).
- Closed (after success): anonymous GET answers `303` with `Location: /auth/login`; a signed-in browser is redirected on to /today by the login page.
- Mismatch: 422, "▲ The two passwords do not match." visible in `#setup-confirm-error`, confirm field `aria-invalid=true` and `aria-describedby=setup-confirm-error`,
  password fields come back empty, token and name and email kept.
- Weak password (browser `minlength` bypassed with novalidate): 422, "▲ Use at least 12 characters." in `#setup-password-error`, password `aria-describedby` switches from the hint to the error.
- 429: status 429 with `Retry-After`, visible alert (`role=alert`) "▲ Too many sign-in attempts. Please wait a few minutes and try again.", form kept, no user created.
- Success: browser lands on `/today` (URL asserted), app shell shown.

### Comparison with force-password.html and invite.html

Screenshots of both handoff pages (1440 and 375) next to the setup page. Same family: bake column with brand and headline (stacked orange bar on the phone),
display-type title, mono lede, uppercase mono field labels, pill inputs, 12+ hint, orange (lime in dark) block pill button `[ create account ]`, `▲` error under the
field in the field-error colour. Field order and spacing equal invite.html (name, email, password, confirm; setup has no readonly invited-by line, as designed). The alert box on 429 sits
between lede and form like the login error. Dark: palette and error colour readable, focus ring visible on the autofocused name field.

### Step 3b

| Check | Result |
|---|---|
| Failing submits show a visible error and write no user row | ok: mismatch, weak password, throttled each left users=1 (the migration's seeded system user, unchanged) and audit_log=0 (throttled: 1 throttle audit row, no user) |
| Success: exactly one user plus audit | ok: users 1 to 2, audit rows 0 to 5 (categories x3 seeded for the new user, `setup_token` consumed marker with user_id 2, session create) |
| /setup closed afterwards | ok: 303 to /auth/login |
| Forced 500 on POST | page shows the raw intercepted body only because the stub returned plain text; the stock error handler is not part of this change; no user row written. Not a setup template finding |
| Labels | ok: every field has a `label[for]` (name, email, password, confirm password) |
| autocomplete | name=`name`, email=`username` (same as invite.html, the design's value for the identity field), password and confirm=`new-password` |
| Error wiring | ok: `aria-describedby` and `aria-invalid` set on the failing field only; password falls back to the hint id |
| Focus order | name (autofocus), email, password, confirm, create button, then page chrome (skip link, brand link); matches visual order |
| HTMX | none on the page (0 hx-* attributes), no swap targets or listeners |
| Template logic | rg of `pages/auth/setup.html` for `style=`, `{% set`, `float`, `/ 100`, `* 100`: no hits; no arithmetic |
| Money formatting, service-number comparison | not applicable: no numbers rendered |

## Verdict (independent audit)

CLEAN. Diagnostics all 0 on 37 rows. Minor notes, not blocking: (1) the 429 alert reuses the sign-in wording ("sign-in attempts") on the setup page;
(2) the 404 body is JSON, not an HTML page, by the "bare 404" design; (3) the brief lists email autocomplete as `email`, the page uses `username` like invite.html (kept for password managers).
