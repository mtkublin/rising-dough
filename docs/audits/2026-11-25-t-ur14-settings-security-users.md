# Frontend probe audit: T-UR14 settings security and users

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
