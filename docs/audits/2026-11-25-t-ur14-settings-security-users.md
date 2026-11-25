# Frontend visual audit: T-UR14 settings security and users

Task: T-UR14, branch wi/ui/sourdough/UR14, head b7034ccc. ADR-0027, ADR-0107, ADR-0152, ADR-0134. Skill: frontend-visual-audit (visual-auditor run, 2026-11-25),
preceded by the implementer's probe (kept at the end of this file).
Method: Playwright chromium against uvicorn (dev env, prod CSP) on a scratch copy of data/demo.sqlite migrated to head (never data/budget.sqlite). Seed: admin plus
Ola, Ewa (must change password), Zed; 4 sessions (iPhone Safari, Windows Chrome, Linux Firefox, plus the browser's own) and 2 seeded passkeys (a third added through a
CDP virtual authenticator on http://localhost). Light and dark through localStorage rd-theme, reduced motion, captures after dialog[open], screenshots with animations
disabled. Heavy lock /tmp/ui-redesign-heavy.lock taken and released. Screenshots (scratch, not committed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur14/shots/<state>__<width>__<theme>.png;
handoff boards rendered to /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur14/hand/.

## Routes and states (69 rows = 11 states x 3 widths x light/dark + force-password x 3 widths)

/settings/security: security-normal (password form, 2 passkeys, 5 sessions with device labels), security-422-empty, security-422-wrong-current ("4 attempts left"),
security-429 (throttled). /settings/users: users-list, users-edit-dialog, users-edit-422, users-delete-confirm, users-delete-blocked-self, users-reset-confirm,
users-one-time-password. Forced rotation page (served at /settings/password for a must-change user): force-password (1440, 1024, 375, light).
Last-admin blocked is the same service guard as self (the only admin is the actor); the self variant was captured.

## Diagnostics

| Route / state | Width | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| all 11 states, light and dark | 1440 | 0 | 0 | 0 | 0 | 0 |
| all 11 states, light and dark | 1024 | 0 | 0 | 0 | 0 | 0 |
| all 11 states, light and dark | 375 | 0 | 3 (a.rd-tabs__tab, inside the scrolling tab strip) | 0 | 0 | 0 |
| force-password | 1440, 1024, 375 | 0 | 0 | 0 | 0 | 0 |

consoleErrors excludes the browser's own "Failed to load resource ... 4xx" line for a deliberate 4xx the page handles (49 over the run: 422 on empty, wrong-current
and edit-422, 429 on the throttle loop); no JS error, no pageerror, no CSP violation, no broken image. The 3 overflowing tabs at 375 are the sideways-scrolling
tab strip (handoff parity, as in T-UR13); the document does not scroll sideways.

## Handoff comparison (side by side at 1440 and 375)

Compared: pages/settings/security.html, security--error.html, users.html, pages/overlays/edit-user.html, delete-user.html, reset-password.html, one-time-password.html
(the overlay boards live in pages/overlays/, not in pages/settings/). Hero band, tab pills, outlined cards, password row grid and hint, sessions ledger (375
reflow identical: values wrap under the device), users ledger, row menu, edit dialog (460px, read-only email, member/admin segmented), bottom sheet at 375 all match.
Differences accepted as derived.md T-UR14 / T-UR20 rows: passkey list instead of the empty state, 422 summary block, current-device sign out, no flash after the
password redirect, no add / invite buttons (T-UR20), no copy button, is_admin radios. "This device" / "You" vs handoff "THIS DEVICE" / "you" kept by contract.
Not accepted, see findings: error flash style, one-time password spacing.

## Step 3b

- Swap targets: password form hx-target="this" (1 match, form re-rendered); edit and delete dialog forms target #user-row-N (1 match before, row replaced after, 0 for
  delete); reset form and row-menu links target #modal-root (1 match). Duplicate ids after every swap: 0 (edit, role change, reset, delete, session revoke).
- Failing saves, forced 404, 409, 500 on the password form, edit, delete and reset (POST intercepted): a flash appears each time with the status copy and the form or
  dialog is not left looking saved (dialog stays open). A real stale delete (user already deleted) gives "User not found". The 429 in a real browser (6th wrong attempt)
  swaps in the form: "Too many attempts. Please wait a few minutes and try again." (app-toast.js change works). Crafted self-delete answers 409 with dialog-close.
  Visibility is weak, see F1. Plain revoke forms, see F2.
- Success flows: edit (name, then role to admin): row updated in place, "Saved ola@example.test." flash, #modal-root empty, no open dialog, DB name and is_admin updated,
  audit row. Delete: row gone (4 to 3 rows), "Removed zed@example.test." flash, #modal-root empty, soft-deleted. Reset: one-time password dialog with a 22-char value,
  done closes it (F4 note). Session revoke: row gone (6 to 5), page back on /settings/security#sessions, no flash (F2). Passkey remove: row gone, no flash (F2).
  Passkey add through a virtual authenticator: new row "Virtual key" after the reload. Password change success: 303 to /settings/security, other sessions revoked (1 left).
  Revoking the current session: redirect to /auth/login, the session cookie is gone, GET /settings/security then redirects to /auth/login?next=%2Fsettings%2Fsecurity.
- Rendered equals service: session stamps 03:14:44Z shown 25 NOV 04:14 (Europe/Warsaw, UTC+1), expiry column is absolute_expires_at (created + 30 days, same value as the
  old page), passkey added 25 NOV 04:14 / last used "never"; device labels Chrome · Windows, Firefox · Linux, Safari · iPhone, Chrome · macOS equal domain.user_agent.device_label
  for the stored user agents; "4 attempts left" after one wrong attempt equals limit 5 minus count 1 (services.rate_limit.attempts_left, tightest of the minute and hour windows).
- Templates (13 changed or new files vs the merge base): rg for float, / 100, * 100, {% set, style=, strftime and arithmetic in expressions: 0 hits (the only operator
  hits are hyphens in field names and the `~` string join of min_length).
- HX-Trigger events: toast and dialog-close have listeners in app-toast.js; no other emitter on these routes.

## Findings

F1 (Behavior / Content, medium, shell-level): the error flash for 404, 409, 500 and a stale delete is rendered unstyled, as plain text with a bare x button, no
rd-flash box and no warning mark, in #flash-region-assertive; with a dialog open it sits dimmed behind the backdrop (top-layer dialog) and the page content shifts 42px.
errors.py renders partials/_flash.html (old shell partial) instead of fragments/flash/error.html (rd-flash rd-flash--error); the success flash is styled. The error is
visible but easy to miss next to the still-open dialog. Screenshots: shots/forced-edit-user-500__1440__light.png, shots/stale-delete-user__1440__light.png.
F2 (Behavior, low, pre-existing on ui/sourdough): the session sign out and passkey remove forms are plain POSTs. A stale id (already revoked in another tab) navigates the
page to a raw {"detail":"not_found"} JSON body (shots/stale-session-revoke__1440__light.png); a successful revoke redirects with no flash (row disappears, nothing says
"signed out"). derived.md only records the missing flash after the password redirect.
F3 (Layout, low): one-time password dialog, the paragraph sits about 10px above the value field (3 lines at 1440, 4 at 375 because of the extra "sessions signed out"
sentence); the handoff leaves about 32px. shots/users-one-time-password__1440__light.png.
F4 (Behavior, info): after "done" on the one-time password dialog #modal-root keeps the closed dialog markup (0 open dialogs, no duplicate ids); edit and delete success
empty it. Replaced on the next open.
F5 (info, not UR14): topbar "settings" has no current-page state on these pages (handoff shows the pill); recorded in the T-UR13 audit.
No arithmetic, float or style= in templates; all five diagnostics are 0 (see table).

## Implementer probe (kept)

### Probe record: frontend probe audit: T-UR14 settings security and users

Task: T-UR14, branch wi/ui/sourdough/UR14. ADR-0027, ADR-0107, ADR-0152, ADR-0075. A visual-auditor runs after this item; this is the implementer's probe.
Method: Playwright (chromium) through the e2e `live_server` + `page` fixtures (prod CSP in force, dev cookies), throw-away driver deleted after the run, light and dark
via `localStorage rd-theme`, animations off, captures after `dialog[open]`. Heavy lock /tmp/ui-redesign-heavy.lock taken and released.
Scratch data only (a fresh migrated temp DB with the login user promoted to admin, two extra users Ola and Ewa (one with a pending password change), a second
iPhone session and two passkeys). `data/budget.sqlite` not touched.

## Routes and states

/settings/security: normal (passkey list, two sessions), 422 error (empty submit); /settings/users: list, row menu open, edit dialog (Ola), delete confirm
(Ola), delete blocked (own account, opened with `htmx.ajax('GET', '/settings/users/1/delete')`). 7 states x 3 widths (1440, 1024, 375) x light and dark = 42 rows.

## Diagnostics

| State | horizontalScroll | duplicateIds | consoleErrors | requestFailures | overflowingElements |
|---|---|---|---|---|---|
| all 7 states, 1440 and 1024, both themes | 0 | 0 | 0 (see below) | 0 | 0 |
| all 7 states, 375, both themes | 0 | 0 | 0 (see below) | 0 | 3 `a.rd-tabs__tab` |

Console lines: the deliberate 422 (empty password change) and, in the throttle journey, the 429 are logged by the browser as "Failed to load resource"; nothing else.
The three overflowing tabs at 375 sit inside `.rd-tabs` (`overflow-x: auto`, the strip scrolls sideways): handoff parity, as recorded for T-UR13.

## Comparison with the handoff boards (settings/security, security--error, users; overlays/edit-user, delete-user, one-time-password)

Hero band with the email note, tab pills, outlined cards, the two-column password row with the spacer, the 12+ characters hint, the sessions ledger, the users ledger
with `● active` / `◐ new password required at next sign-in`, the row menu (edit, reset, delete in danger tone, own row without menu), the edit dialog (read-only email,
name, member/admin segmented), and the confirm and blocked dialogs match in structure and spacing. Phone: the dialog is a bottom sheet, user rows wrap role and last
seen under the email. Derived or deviating items are rows in `derived.md` (task T-UR14 / T-UR20): passkey list, 422 summary, current-device sign-out, no flash after the
password redirect, add and invite buttons left to T-UR20, `is_admin` radios, one-time password without a copy button, minimal forced page.

## Findings

1. Fixed here: a throttled password change (429) was never swapped in by the new shell (htmx skips 4xx except the 422 `htmx-csrf.js` allows), so the wait message
   stayed invisible. `rd/js/app-toast.js` now lets the 429 swap; covered by the journey `test_throttled_password_change_shows_the_wait_message_in_the_form`.
2. Crawler: the revoke button of the current device clears the browser's session cookie, which a DB restore cannot bring back; `tests/e2e/crawl/engine.py` now
   skips it by name (like the logout button) and matches `SKIP_NAMES` case-insensitively (the new shell prints lower-case names, `add passkey`).
3. Not mine: the topbar `settings` link has no current-page state (as in the T-UR13 audit).

## Step 3b

- Templates (pages/settings/security, users; fragments/forms/password-form, one-time-password; rows/session-row, passkey-row, user-row; tables/users-table;
  dialogs/edit-user, delete-user, reset-password, one-time-password): no `{% set`, `float`, `/ 100`, `* 100`, `strftime`; stamps (`12 NOV 09:14`), roles, status text,
  the blocked reason and the menu items are view-model values (`web/settings_view.py`); G9 allowlist entries of T-UR14 deleted (72 to 63).
- Rendered equals service: the sessions table prints `created_at`, `last_seen_at` and `created_at + 30 days` in the display timezone (integration test compares with
  `clock.now_in(...)`); the device label is `domain.user_agent.device_label` (`Safari · iPhone`); attempts left come from `services.rate_limit.attempts_left`.
- Every failing save shows an error: empty password change (422, summary and `▲` lines, role alert), throttled change (429, wait message), edit dialog with a changed
  email (422, summary in the dialog), guard 409 (flash, dialog closes).
