# Frontend visual audit: F3 settings handoff parity (2026-11-25)

Change: item F3 (ui-redesign, settings handoff parity), branch `wi/ui/sourdough/F3`.
Audited at commit `11364e3` (descendant of the brief's `d90bc70`: the implementer added `5b36dbf` and a MAIN merge while the audit was queued; the whole sweep was re-run on `11364e3`).
Tool: `frontend-visual-audit` skill (Playwright, headless Chromium). Scratch DB built by `tests/visual/handoff_seed.py` (`build_seed`), server via `tests.visual.frozen_server` with the clock frozen at 2026-10-31 (as `tests/visual/conftest.py`). `data/budget.sqlite` was not touched.
Dialogs were opened the way the page openers do it (`htmx.ajax GET` into `#modal-root` from the host page).

## Routes x viewports (1440, 1024, 375)

| Route / state | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| /settings?tab=categories | false x3 | 0 / 0 / 3 (tabs, see below) | 0 | 0 | 0 |
| /settings?tab=prefs | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| /settings?tab=fx | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| /settings/security | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| /settings/security, wrong current password (422) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 (1 expected 422 resource line) | 0 |
| /settings/users | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /categories/new | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /categories/new, blank name (422) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 (expected 422 line) | 0 |
| dialog /categories/new, name Takeaway (422) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 (expected 422 line) | 0 |
| dialog /categories/19/edit | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /categories/19/archive | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /settings/users/new | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /settings/users/new, used email (422) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 (expected 422 line) | 0 |
| dialog /settings/users/2/edit | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /settings/users/3/delete | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /settings/users/2/reset-password | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| reset-password submitted (one-time password dialog, copy button) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog /settings/users/invites/new | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| dialog invites/new, existing account (422) | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 (expected 422 line) | 0 |
| dialog /settings/users/invites/1/revoke | false x3 | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |

Totals: horizontalScroll=0, overflowingElements=0 at 1440 and 1024, duplicateIds=0, consoleErrors=0, requestFailures=0.
The only "console error" lines are the browser's own `Failed to load resource ... 422` for the deliberately forced 422 submits (8 per viewport set), each paired with the visible inline error below; none on a plain load.

### overflowingElements at 375 (pre-existing, not blocking)

Three `a.rd-tabs__tab` (right edges 403, 504, 581) on every settings page at 375. `document.scrollWidth` does not exceed the viewport (horizontalScroll false): `.rd-tabs` is an intentional `overflow-x: auto` strip (scrollWidth 549 > clientWidth 311, `app.bundle.css` `.rd-tabs`). F3 changes no CSS. The same three elements and numbers were measured on MAIN (`ui/sourdough` 58624ad, same seed) for /settings?tab=categories and /settings/security at 375: identical, so pre-existing.

## Step 3b

- Swap targets: every `hx-target="#..."` on every audited page matched exactly one element (0 mismatches); no duplicate ids after the 422 swaps or the reset-password swap.
- Failing saves visible (forced real 422s): blank category name shows "Some fields need fixing: Name"; duplicate "Takeaway" shows inline "A category with this name already exists" (POST 422, no 500); used email shows "A user with this email already exists"; invite for an existing account shows "This person already has an account"; wrong current password on /settings/security shows "Current password is wrong" under the field. Forced 404/409/500 via `page.route` were not run.
- One-time password dialog: reset-password POST 200, password shown once, copy button click shows "copied" and the clipboard holds the 22-character password (all three widths).
- Template logic: `rg` over the 13 touched templates for `float`, `/ 100`, `* 100` and `{% set %}`: no hits.
- Security page sessions: the current device row ("THIS DEVICE") has no sign-out button; the other session (Safari, iPhone) has exactly one. Text check: 2 "sign out" in page text = topbar + that one row, at all widths.
- No money figures are printed by these pages; the money-by-currency and service-equality checks do not apply.

## Findings

None blocking. Notes: the 375 tab strip overflow above (pre-existing on MAIN).

## Screenshots

`/tmp/fe-audit-f3/<viewport>__<name>.png` (60 full-page PNGs plus `.txt` page texts and `summary.json`; run on `11364e3`; an earlier run on `5b36dbf` gave identical results at `/tmp/fe-audit-f3-run1/`). Viewed: 1440 duplicate-name dialog (inline error visible), 1024 users page, 375 one-time-password dialog (fits, copy button shows "copied"), 375 security page with the wrong-password error. In the full-page captures the modal backdrop covers only the first viewport and the fixed bottom bar appears mid-page at 375; both are capture artefacts.
