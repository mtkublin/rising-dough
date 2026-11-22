# Frontend audit: T-Q204 admin edit form sends a hidden is_admin=0

Change: T-Q204 (Q-063, ADR-0137). `templates/settings/users/edit.html` gains
`<input type="hidden" name="is_admin" value="0">` before the Admin checkbox so that an absent `is_admin`
field can mean "unchanged" on the server while an unchecked box still demotes (last value wins).

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q204.sqlite` (never `data/budget.sqlite`), logged in through the password form as
a scratch admin.

## Routes and diagnostics

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /settings/users | 1440 | false | 0 | 0 | 1 (script URL, see triage) | 0 |
| /settings/users/1/edit | 1440 | false | 0 | 0 | 1 (same) | 0 |
| /settings/users | 1024 | false | 0 | 0 | 1 (same) | 0 |
| /settings/users/1/edit | 1024 | false | 0 | 0 | 1 (same) | 0 |
| /settings/users | 375 | false | 0 | 0 | 1 (same) | 0 |
| /settings/users/1/edit | 375 | false | 0 | 0 | 1 (same) | 0 |

Triage: the single console error per session is the audit script's own doing, not a broken link. The real
login route is `/auth/login`; the script opened `/login`, which redirects (302) to `/auth/login?next=%2Flogin`,
and after sign-in the app redirected to `next=/login`, which is not a route (404). It is emitted before any audited
route loads, the counter does not grow across the audited routes, and no template or route was changed for it.

## Screenshots (viewed)

`/tmp/fe-audit-tq204/{desktop,tablet,mobile}__settings_users.png` and `..._settings_users_1_edit.png`.
The edit page renders the same toggle card as before; the hidden input adds no visible element.

## Step 3b

1. Swap targets: `hx-target` / `hx-swap` attributes of the edit form are untouched by the diff.
2. Failing saves: the 409 (last admin) and 422 paths still render their flash; covered in
   `tests/integration/web/test_settings_users.py` (`test_demote_last_admin_refused`, duplicate-email tests).
3. No arithmetic or `float` in the template; none added.
4. Money formatting: N/A.
5. Rendered equals service: N/A (no numbers); the posted values are asserted in
   `test_edit_form_sends_hidden_zero_so_unchecked_box_demotes` and `test_hidden_zero_then_checked_box_keeps_admin`.
6. Duplicate ids: 0 on every route and viewport; the hidden input has no id.
7. Scratch data only: yes.
