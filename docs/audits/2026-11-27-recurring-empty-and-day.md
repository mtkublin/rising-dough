# Frontend audit: recurring empty state and day of month (RECUR)

Date: 2026-11-27. Item RECUR, branch wi/ui/sourdough/RECUR, audited sha 0015edb7. Tasks T-UR78 (R18), T-UR79 (R19).
Run with the frontend-visual-audit skill (Playwright, Chromium) against a scratch copy of data/demo.sqlite (migrated, login user seeded; one copy with all recurring rules soft-deleted for the empty state, one normal copy with 27 rules), env=dev, 127.0.0.1. data/budget.sqlite untouched. MAIN (ui/sourdough 16010c5a) was run against the same populated copy for the pre-existing comparison.

Change: `fragments/states/recurring-empty.html` new-entry link now hx-gets into `#modal-root`; new `static/rd/js/recurring-day.js` (loaded from `layouts/base.html`) fills day of month from the start date until the user types in it.

## Routes and diagnostics

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| /ledger?view=recurring, empty state | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| same, new-entry dialog on repeats tab | false/0/0/0/0 | false/0/0/0/0 | false/1/0/0/0 (a) |
| same, after a submit blocked by native validation (b) | false/0/0/3/0 (c) | false/0/0/3/0 (c) | false/1/0/3/0 (a, c) |
| same, after save (rule listed, flash shown) | false/0/0/3-4/0 (c) | false/0/0/3-4/0 (c) | false/0/0/3-4/0 (c) |
| same, reload with the rule listed | false/0/0/4/0 (c) | false/0/0/4/0 (c) | false/0/0/4/0 (c) |
| /ledger?view=recurring, populated (27 rules) | false/0/0/0/0 | false/0/0/0/0 | false/1/0/0/0 (d) |
| edit-recurring dialog (rule 21) after start date change | false/0/0/1/0 (e) | false/0/0/1/0 (e) | false/2/0/1/0 (d, e) |
| edit dialog, 422 save (start cleared, day 15) | false/0/0/3/0 (e) | false/0/0/3/0 (e) | false/2/0/3/0 (d, e) |

Notes:
- (a) `label.rd-chip-option` ends at 377 px (2 px past the viewport) in the repeats form; no horizontal scroll. Same element overflows on MAIN in the edit-recurring dialog (same chip), so pre-existing; the diff does not touch it.
- (b) Clicking [ save ] with the amount empty is stopped by the browser's native required validation ("Please fill out this field"), so no POST is sent; the server-side 422 path is covered by the edit dialog row and the forced responses below.
- (c) Console errors are only "Failed to load resource ... 422" for POST /recurring/formula/preview (the live formula preview answers 422 while the formula is empty) and, in the later rows, accumulated earlier ones. No CSP violation event (a `securitypolicyviolation` listener was installed before navigation) and no pageerror on any page. Not caused by this change.
- (d) 375: `a.rd-tabs__tab` right edge 380 (recurring tab) and `label.rd-chip-option` 402; identical on MAIN.
- (e) 422 x1 on start change and x3 after save in the edit dialog: POST /recurring/formula/preview, plus the deliberate 422 of POST /recurring/21. Identical counts and URLs on MAIN (run against ui/sourdough 16010c5a), so pre-existing, not from this change.

Screenshots (viewed: empty state, dialog, after-save at 375, failed save at 1440; the rest are captured, diagnostics read from JSON): scratchpad dirs `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots-empty` (01-empty, 02-dialog-repeats, 03-failed-save, 04-after-save, 05-listed-reload per width), `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots-pop` (10-populated, 11-edit-dialog, 12-edit-failed-save), `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots-forced`.

## Behaviour (T-UR78, T-UR79)

- Empty state: the link has `hx-get=/add?when=happened&dialog=1`, `hx-target=#modal-root`; clicking opens the dialog, the URL stays /ledger?view=recurring (no navigation to a bare fragment). At 1440/1024 there are two "[ new entry ]" links (top bar and empty state), at 375 one.
- Repeats -> category, amount 50.00, save: POST /recurring 200, dialog closes, the same page lists the rule (50.00, "1 rules", next due), no empty body, flash "Recurring rule saved" shown. 1440, 1024 and 375.
- New entry, repeats: start 2026-12-06 -> day 6; start 2026-12-09 (day untouched) -> day 9; typed 15 then start 2026-12-20 -> day stays 15. Default (start today 27/11) shows day 27. Stored day of the saved rule matched the field (15 after typing).
- Edit-recurring dialog of rule 21 (day 1, start 2026-11-01): changing the start date to 2027-03-17 leaves day at 1. Server-rendered values count as typed, never overwritten (same as the brief; MAIN behaves the same, there is no JS there).
- Failing save in the edit dialog (start cleared, day typed 15): dialog stays open, field error "invalid date" visible, day still 15.
- Script load: `<script type="module" src=...recurring-day.js>` is an external same-origin module like its neighbours; no CSP violation on any page.

## Step 3b

1. Swap targets: `#modal-root` count is 1 before and after the dialog swap (checked in each forced run).
2. Failing saves visible: POST /recurring forced to 404, 409 and 500 from the open repeats dialog (all fields filled): dialog stays open and shows "That item was not found. It may have been removed." / "That item changed in the meantime. Reload and try again." / "Something went wrong on our side. Try again." respectively. Not left looking saved. 422 shown as field errors (edit dialog).
3. No arithmetic in templates: the template diff (recurring-empty.html, base.html) adds no float, `/ 100`, `* 100` or `set`; the day computation lives in the JS file (string slice of the ISO date, no money).
4. Money formatting by currency: not touched by this change (no amount rendering added); rule list amounts go through the existing filters. JPY not re-checked: out of scope of the diff.
5. Rendered numbers: saved 50.00 shows as -50.00 PLN in the hero and the row; the stored amount 50.00 PLN matches (DB probe: one rule, start 2026-12-06, day as typed).
6. Duplicate ids: 0 after every swap (empty -> dialog -> after save, and edit dialog). No new HX-Trigger emitters or listeners added by the diff.
7. Scratch data only.

## Findings

None new. Pre-existing on MAIN, not blocking for this item: formula-preview 422 console noise on start change and 2 px chip overflow at 375 (details above).
