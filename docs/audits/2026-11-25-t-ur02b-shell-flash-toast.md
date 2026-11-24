# Frontend visual audit: T-UR02b shell flash regions, toast renderer, topbar email

Task: T-UR02 follow-up (UR02b), branch wi/ui/sourdough/UR02b at 76eed541 (merges ui/sourdough 10cf35bb). ADR-0027, ADR-0143, ADR-0150.
Method: frontend-visual-audit skill (Playwright, chromium), heavy lock /tmp/ui-redesign-heavy.lock taken and released.
Scratch data only: a copy of data/demo.sqlite with the seeded login user (no write to data/budget.sqlite).
Screenshots (viewed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR02b2/shots/ (state-theme-width .png).

## Routes and diagnostics

Routes: /today, /accounts, /plan?tab=budget (signed in, normal state), /dev/shell (idle, after toast, after 409 flash, after 500 flash),
/auth/login (signed out). Each at 1440, 1024, 375, light and dark (56 rows).

| Route / state | 1440 L/D | 1024 L/D | 375 L/D |
|---|---|---|---|
| /today | hs=0 ov=0 dup=0 con=0 rf=0 | same | hs=0 ov=1 (pre-existing, see F3) dup=0 con=0 rf=0 |
| /accounts | 0/0/0/0/0 | same | same |
| /plan?tab=budget | 0/0/0/0/0 | same | same |
| /dev/shell idle | 0/0/0/0/0 | same | same |
| /dev/shell after toast | 0/0/0/0/0 | same | same |
| /dev/shell after 409 | hs=0 ov=0 dup=0 con=1 rf=0 | same | same |
| /dev/shell after 500 | hs=0 ov=0 dup=0 con=1 rf=0 | same | same |
| /auth/login | 0/0/0/0/0 | same | ov=1 (pre-existing, see F3) |

consoleErrors=1 on the 409 and 500 rows is only the browser's own "Failed to load resource ... 409/500" line for the deliberately
forced response; there is no script error. horizontalScroll=false and requestFailures=0 (requestfailed plus HTTP >= 400 other than the
forced ones) in all 56 rows. duplicateIds=0 in all rows, also after repeated flashes (see below).

Topbar email: owner@example.test is rendered before "sign out" and visible at 1440 and 1024 (both themes) on /today, /accounts,
/plan and /dev/shell; at 375 the element exists but is hidden (u-hide-below-md, display none); /auth/login has no topbar email at any width.
Shell: body data-today-local=2026-11-25 on every signed-in route; #flash-region (role=status, aria-live=polite) and
#flash-region-assertive (role=alert, aria-live=assertive) both exist once with class rd-flash-region.

## Failed-save path (UR07a/UR08a re-check), 1440 and 375

Real handler output was used: the flash body of /dev/shell/fail/<status> fulfilled the request through page.route (404/409/500), a stale id
rewrite for a real 404, and a real 409 on /accounts/10/delete.

| Action | 404 | 409 | 500 |
|---|---|---|---|
| Today row menu skip /recurring/<id>/skip-next | SILENT (F1) | flash "Dev conflict: that row is protected" in #flash-region | assertive flash "Something went wrong on our side. Reference: ..." |
| promote all due (1440 only; the button is display:none at 375 by the board design) | SILENT (F1) | flash | assertive flash |
| Accounts row menu delete /accounts/<id>/delete | SILENT (F1) | flash, row kept | assertive flash, row kept |
| Accounts delete, real 409 (account 10, 30 transactions) | - | "Cannot archive account: Balance is not zero; 30 transactions use this account", row kept, 20 rows before and after | - |

Two errors in a row (/dev/shell, 409, 500, 409, 500): both regions keep id, role, aria-live and class rd-flash-region, exactly one element per id,
the content is replaced (not appended; childEls=1), and the latest message shows (500 reference changed on every repeat). The polite and the
assertive region are independent, so a 409 and a 500 stay visible together (F4, note). Dev toast: "Dev toast saved" with undo, auto-arm, matches the board.

## Comparison with the handoff (pages/today--flash.html; there is no overlays/toast*.html)

Toast (pill at the bottom above the tab bar on 375, text plus undo action, light and dark) matches the board. Flash: the board shows
rd-flash--success/--error with an icon-less dot, a retry action and a close button; the app shows the old plain .flash markup (text and a
bordered x). Known and accepted until T-UR15 (derived.md), confirmed. Topbar email placement (before sign out, muted, md up) is pending
designer confirmation, confirmed as accepted.

## Step 3b

- Templates touched (layouts/base.html, pages/dev/shell.html): rg for style=, float, / 100, * 100, set blocks: no hits; no arithmetic inside
  {{ }} (only url_for paths). Main has 0 style attributes on all audited routes.
- Swap targets: every id/class hx-target matches exactly one element on every audited route before and after the swaps (tgbad empty), the
  regions keep a single id after four consecutive flashes. dup ids 0.
- Failing saves visible: yes for 409 and 500 on all three actions; NOT for 404 (F1).
- Rendered numbers: UR02b adds no figures to templates; the pages' numbers are untouched by this change.
- Listeners: toast event has a listener (app-toast.js) and an emitter (toast_payload); htmx:beforeSwap handler copies the OOB flash children.

## Findings

F1 (Behavior, blocking). A 404 on an HTMX action is silent: the response is the plain text "not found" (no OOB flash), the beforeSwap
   handler does not match, htmx only logs "Response Status Error Code 404" to the console. Reproduced on Today skip (real stale id and forced),
   promote-all (forced) and Accounts delete (forced). 409 and 500 are fine. Fix: HTMX 404 responses (web/errors.py HTTPException handler for
   HX-Request) should carry the same flash-only OOB body as 409/500. Shots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR02b2/shots/today-skip-forced404-1440.png, today-promote-forced404-1440.png, accounts-delete-forced404-1440.png, today-skip-real404-375.png.
F2 (Behavior, blocking against the brief). A successful Today skip shows no toast and no undo: /recurring/<id>/skip-next answers 200 with
   only HX-Trigger {ledger-stale, forecast-stale, budget-stale}, hx-swap=none, so the page does not change either (1440 and 375). The toast
   renderer itself works (/dev/shell toast). Fix: the skip route emits toast_payload with an undo, or a swap. Shot: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR02b2/shots/today-skip-success-1440.png.
F3 (Layout, low, pre-existing on ui/sourdough 10cf35bb, identical there): the decorative ASCII loaf (pre.rd-hero__loaf on /today at 375,
   right=399; pre.rd-auth__loaf on /auth/login at 375, right=407) extends past the viewport; no horizontal scroll results. Not caused by UR02b.
F4 (Behavior, note): a polite flash is not cleared when an assertive one arrives (and the reverse), so a stale message can remain next to the new one.
F5 (Behavior, note, server): POST /accounts/99999/delete (unknown id) answers success; the UI removes the targeted row and shows the
   "Account deleted" toast although nothing was deleted. Pre-existing, outside UR02b.
