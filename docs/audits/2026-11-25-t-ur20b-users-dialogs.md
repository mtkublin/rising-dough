# Frontend visual audit: T-UR20b add-user dialog and one-time password (users dialogs)

- Item: UR20b (T-UR20 slice b), branch `wi/ui/sourdough/UR20b`, audited at `bda92268`.
- Method: `frontend-visual-audit` skill, headless Chromium, own server on 127.0.0.1:8791 over a migrated scratch copy of `data/demo.sqlite` (never `data/budget.sqlite`). Heavy lock `/tmp/ui-redesign-heavy.lock` taken and released.
- Screenshots (all viewed in part; key ones read): `/tmp/fe-audit-ur20b/<1440|1024|375>__<step>.png`, per-viewport results `/tmp/fe-audit-ur20b/res-<vp>.json`.

## Routes x viewports

Routes: `/settings/users` (list, add dialog, 422 dup and invalid, one-time password dialog, forced 500, row menu, edit, reset, delete, blocked 409 flashes) and `/settings/password` (forced change as the added user, failing saves). Each at 1440, 1024 and 375.

| Route (states) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /settings/users (20 states) | 1440 | false | 0 | 0 | 0 (*) | 0 |
| /settings/password forced (4 states) | 1440 | false | 0 | 0 | 0 (*) | 0 |
| /settings/users (20 states) | 1024 | false | 0 | 0 | 0 (*) | 0 |
| /settings/password forced | 1024 | false | 0 | 0 | 0 (*) | 0 |
| /settings/users (20 states) | 375 | false | 3 (**) | 0 | 0 (*) | 0 |
| /settings/password forced | 375 | false | 0 | 0 | 0 (*) | 0 |

(*) The only console lines are the browser's "Failed to load resource" for the HTTP statuses this audit forces on purpose (422 x2, 500, 409 x2 on the users page; 422 x2 on the password page). No script errors, no unexpected statuses.

(**) 375: three `a.rd-tabs__tab` (settings tabs) extend past the viewport; `horizontalScroll` is false because the strip is a sideways scroller (the "prefe..." tab is cut, as designed). The tabs fragment is untouched by this slice (`git diff ui/sourdough...HEAD` lists no tabs file); the same count shows on every settings page. Pre-existing, not blocking. `/today` after the forced change shows `pre.rd-hero__loaf` right=399 at 375 (existing hero art, outside this slice).

## Behaviour checks (50 per viewport, 0 failing apart from the one noted below)

- `+ add user` opens `#dlg-add-user` with email, name, member/admin radios (member preselected), cancel and `[ add user ]`. At 375 the cancel button is hidden by the shared sheet CSS (`dialog.css` hides `.rd-btn--quiet[data-js=dialog-close]` on phones; the X closes). Same as every dialog; not a finding.
- Invalid email: 422, dialog stays open, summary at top ("1 field needs attention", link to Email), email field `aria-invalid="true"`, "▲ Enter a valid email address.", typed email and name kept.
- Duplicate email in other case (`OLA-...@EXAMPLE.COM`): 422, same pattern, "▲ Another user already has this email.", values kept.
- Success: 200, `Cache-Control: no-store`, "one-time password · <email>" dialog with "Shown once. Hand it to Ola; ..." and the password in `#new-password-value`; no toast; `#users-table` refreshed behind with the new row ("new password required at next sign-in").
- Password not retrievable: after done, a reload and reopening the add dialog, the password text is absent from the page.
- Forced 500 on add (route intercepted): error banner "Something went wrong on our side. Try again." appears, dialog stays.
- Edit user: email read-only, name and role saved (DB checked: name renamed, `is_admin=1`), row swapped.
- Reset password: confirm dialog, 200 + `no-store`, one-time dialog for the same email.
- Delete user: confirm dialog says entries stay in the ledger; 200, row gone, user soft-deleted, transactions count unchanged.
- Blocked: own row has no menu; forced POST for self demote and self delete give 409 and a styled "▲ You can't remove your own account. Ask another admin." flash (checked via htmx.ajax); admin row unchanged in DB.
- Forced change: the added user logs in and lands on `/settings/password` ("[ save and continue ]", "sign out instead"); too short (minlength stripped to reach the server) and mismatch both 422 with summary and "▲" field error; a valid save clears `must_change_password` and goes to `/today`.

## Step 3b

- Swap targets: `#modal-root` and `#users-table` match exactly one element before and after each swap. The only `hx-target` that counts 0 is the literal `this` on the password form (a keyword, not a selector).
- Templates (`add-user`, `users`, one-time-password, edit/delete/reset dialogs, users table and row): `rg` for `float`, `/ 100`, `* 100`, `{% set` returns nothing. No money on these pages.
- Failing saves visible: 422 (summary and field error), 409 (flash), 500 (banner) all shown; nothing looks saved.
- Duplicate ids after each swap: 0. HX-Trigger events used here are the existing dialog and flash ones; no new emitter or listener.

## Findings

1. Non-blocking, content: the duplicate-email message reads "Another user already has this email." while the handoff `overlays/add-user--error.html` reads "A user with this email already exists". The wording comes from the shared service message; triage or align.
2. Triaged, pre-existing: 375 tabs strip `overflowingElements` (see (**)).

No blocking findings.
