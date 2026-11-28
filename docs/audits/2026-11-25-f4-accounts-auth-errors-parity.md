# Frontend visual audit: F4 accounts / auth / errors handoff parity

- Date: 2026-11-25
- Item: F4 (branch `wi/ui/sourdough/F4`, audited sha `a31db37`, MAIN `ui/sourdough`)
- Skill: `frontend-visual-audit` (Playwright, Chromium headless shell, scripted from the repo's own
  `tests/visual` helpers: `build_seed`, `serve_db`, `handoff_states`)
- Data: scratch DBs only, built by `tests/visual/handoff_seed.py` (base, `invite-expired`, `invite-used`)
  and `handoff_states.build_empty_db` (first-run setup). `data/budget.sqlite` was not touched.
- Server env: `BUDGET_ENV=dev` (dev failure routes mounted), frozen date `2026-10-31`;
  setup server env from `handoff_states.setup_server_env()`.
- Screenshots: `/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/fe/<vp>__<state>.png`
  (session scratchpad, not committed; viewed: login failed 1440/375, 500 page 1440, offline card and
  offline-in-form 1440/375, dialog 422 currency and blank-name 1440/375, 422 page 375, invite expired
  375, invite weak-password 375, setup failed 1440).

## Routes and states (each at 1440, 1024 and 375)

| Route / state | How reached |
|---|---|
| `/auth/login` | unauthenticated |
| `/auth/login` after "forgot password" click | click `[data-forgot-password]` |
| `/auth/login` failed sign-in | wrong password, Enter |
| `/auth/reauth` and failed reauth | signed in, wrong password |
| `/invite/handoff-invite-accountant` (valid), valid + 5-char password submit | base seed |
| `/invite/not-a-real-token` (invalid) | base seed |
| `/invite/...` expired, used | seed modifiers `invite-expired`, `invite-used` |
| `/setup?token=...` and failed submit | empty migrated DB, novalidate, `owner@example` + `short` |
| `/dev/shell/fail/409`, `/dev/shell/fail/500` | plain form POST (browser navigates to the page) |
| 422 page | `GET /plan?tab=forecast&horizon=abc` (ParamError -> `pages/errors/422.html`) |
| Offline card, retry restores | abort `**/today/upcoming*`, click window=30, then unroute and click "retry now" |
| Offline inside a form | abort `POST /accounts` from the new-account dialog |
| `/accounts` | signed in |
| New-account dialog open, 422 currency `XYZ`, 422 blank name (server path, form set `novalidate`) | `+ new account` |

## Diagnostics

Counts per row. `consoleErrors` and `requestFailures` are raw Chromium counts; every non-zero one in
the table below is the browser's own "Failed to load resource" line for an intentional 4xx/5xx
answer or the intentionally aborted request (the state under test), listed in the Expected column.
`overflowingElements` excludes `[hidden]` and `.sr-only`.

| Route / state | hScroll | overflowing | dupIds | console | reqFail | Expected / note |
|---|---|---|---|---|---|---|
| auth_login 1440 / 1024 | false | 0 | 0 | 0 | 0 | |
| auth_login 375 | false | 1 | 0 | 0 | 0 | `pre.rd-auth__loaf` right=407, decorative ASCII art, clipped; pre-existing (see F-1) |
| auth_login_forgot 1440 / 1024 / 375 | false | 0 / 0 / 1 | 0 | 0 | 0 | 375: same `rd-auth__loaf`. Text "Ask the admin to reset your password." shown |
| auth_login_failed 1440 / 1024 / 375 | false | 0 / 0 / 1 | 0 | 1 | 0 | 401 console line; 375: same loaf |
| auth_reauth 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 | |
| auth_reauth_failed (all) | false | 0 | 0 | 1 | 0 | 401 console line |
| invite valid / invalid / expired / used (all) | false | 0 | 0 | 0 | 0 | |
| invite valid, weak password (all) | false | 0 | 0 | 0 | 0 | browser minlength tooltip blocks submit |
| setup (all) | false | 0 | 0 | 0 | 0 | |
| setup_failed (all) | false | 0 | 0 | 1 | 0 | 422 console line |
| dev_fail_409 (all) | false | 0 | 0 | 1 | 0 | 409 console line |
| dev_fail_500 (all) | false | 0 | 0 | 1 | 0 | 500 console line |
| 422 page (`/plan?...horizon=abc`, all) | false | 0 | 0 | 1 | 0 | 422 console line |
| accounts, new-account dialog (all) | false | 0 | 0 | 0 | 0 | |
| dialog 422 currency / blank name (all) | false | 0 | 0 | 1 | 0 | 422 console line |
| offline_card (all) | false | 0 | 0 | 3 | 1 | aborted GET (`ERR_INTERNET_DISCONNECTED`) |
| offline_retry_restored 1440 / 1024 | false | 0 | 0 | 3 | 1 | counters carry over from the aborted request on the same page |
| offline_retry_restored 375 | false | 1 | 0 | 3 | 1 | `pre.rd-hero__loaf` right=399 on restored `/today` hero; Today is not an F4 file (see F-2) |
| offline_in_form (all) | false | 0 | 0 | 3 | 1 | aborted POST |

Totals over the F4-owned states: horizontalScroll=0, duplicateIds=0, unexpected consoleErrors=0,
unexpected requestFailures=0, overflowingElements=1 distinct (pre-existing decorative loaf, F-1).

## Step 3b: behaviour contract and template logic

- Template logic: `rg 'float|/ ?100|\* ?100|\{% ?set '` over `pages/auth`, `pages/errors`,
  `fragments/states/offline-page.html`, `layouts/base.html`, `pages/accounts`: no match.
- Swap targets: on `/accounts` every `hx-target` is `#modal-root` (1 match) before and after the dialog
  swap; the dialog form `#account-form` resolves to exactly 1 element after the 422 swap. No duplicate
  ids after the open, 422-currency and 422-blank swaps at all three widths.
- Failing saves are visible:
  - Sign-in failure: alert "Email or password is incorrect." (401). Reauth failure: "That password
    doesn't match. 4 attempts left."
  - Setup failure: per-field "Enter a full email address", "Use at least 12 characters".
  - Invite expired / used / invalid: alert with a next step and a "back to sign in" link.
  - Account dialog: currency `XYZ` -> "Unknown currency code" under the field; blank name (server
    path) -> "Name is required" under the field; dialog stays open with typed values.
  - 409 page: "Changed elsewhere ... Nothing of yours was saved; reload" with `[ reload ]`.
  - 500 page: "ERROR 500 / Something broke / Nothing was saved. Try again." with `[ try again ]`.
    The reference id is no longer shown. A user still sees an unmistakable visible error with a
    recovery action; only the support correlation id is gone from the full page (the HTMX flash
    variant still prints `Reference: <id>`). Judged acceptable for the user; see F-4.
  - 422 page: summary "1 field needs fixing" with the message and `[ back to the form ]`.
  - Offline: full card "You're offline / retry now" when the Today range request fails; clicking
    "retry now" with the network back removes the card and restores Today. A failed POST inside the
    new-account dialog keeps the dialog and typed values and shows the inline "You're offline ... Your
    input is kept; retry when you're back online" banner with `retry now`; the page behind is not
    replaced by the full card.
- Rendered numbers: `/accounts` hero 34,439.69 PLN = assets 36,895.43 + liabilities -2,455.74 (page
  text); not compared against the service on a second path (F4 changed no number rendering).
- Forgot password: click shows "Ask the admin to reset your password." in the status line.

## Keyboard focus

- `/auth/login` and `/setup`: no autofocus; `document.activeElement` is `body` on load (measured before
  any key press; invite and reauth were only probed by Tab order, not by initial focus). First Tab stops
  on "skip to content", second on the brand link, then the form controls in visual order:
  login: email, password, sign in, passkey button (then forgot-password link); setup: email, name,
  password, confirm; invite: email (read-only, still a stop), name, password, confirm; reauth: password,
  confirm, cancel. No stop is skipped and none is out of order. Expired / used / invalid invite pages:
  skip link, brand, "back to sign in".
- Account dialog open: focus moves into the dialog on the hero amount field (`#field-opening_balance`).
  After a 422 the focus stays on the hero amount, not on the first invalid field (F-3).

## Findings

| Id | Severity | Where | Problem |
|---|---|---|---|
| F-1 | non-blocking, pre-existing | `/auth/login` @375 | `pre.rd-auth__loaf` (ASCII loaf) right edge 407 > 375 viewport: counted by `overflowingElements`, no `horizontalScroll`, visually clipped as designed (`.rd-auth__loaf` has `inset-inline-end: calc(var(--space-8) * -1)` in `static/rd/css/pages/auth.css`). Present on `ui/sourdough` (the loaf markup is in its `login.html`; F4 changed no CSS). The loaf overlaps the end of the "Hello again." headline at 375 (screenshot `375__auth_login_failed.png`). |
| F-2 | non-blocking, out of F4 scope | `/today` @375 (after offline retry) | `pre.rd-hero__loaf` right=399 (same decorative pattern); Today templates untouched by F4. |
| F-3 | a11y, low | account dialog 422 | Focus stays on the hero amount after a validation error; the invalid field (`#field-name`, `#field-currency`) is not focused and there is no summary region. The error text under the field is visible but a screen reader user is not moved to it. |
| F-4 | low | `/dev/shell/fail/500` | Full-page 500 has an empty gap where the reference id used to be (about 100 px between the message and the button at 1440) and no reference id. The visible error and retry action are intact. |
| F-5 | low | 422 page | The summary links are `#field-<name>` anchors (`#field-horizon`) that do not exist on the 422 page itself (they only make sense on the form page). Clicking does nothing visible. |
| F-6 | low, no-JS only | `POST /accounts` without `HX-Request` | Answers 422 with the bare `<dialog>` fragment (no layout), so a no-JS plain POST renders a blank page. Not reachable through the UI (the dialog always posts via HTMX). |

No blocking findings: horizontalScroll, duplicateIds, consoleErrors and requestFailures are 0 apart
from the intentional failing responses and the intentionally aborted request.
