# Frontend visual audit: T-UR04b dialog JS and error summary

Date: 2026-11-24. Branch wi/ui/sourdough/UR04b, commit 13ce19c4 (base 15d05b4b). Task: T-UR04.

Change: layouts/base.html loads rd/js/csrf.js and rd/js/htmx-csrf.js (htmx-csrf adds an htmx:beforeSwap handler that lets 422 bodies swap); new fragments/forms/error-summary.html; new web/dialogs.py response helpers (no route).

Method: frontend-visual-audit skill (Playwright/Chromium, explicit viewports) against a migrated scratch copy of data/demo.sqlite, uvicorn on 127.0.0.1:8767, real login form. Screenshots in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur04b/shots/ (viewed: 1440__error-summary.png, 375__error-summary.png).

## Results

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /dev/shell (new base) | 1440 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 1024 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 375 | false | 0 | 0 | 0 | 0 |
| /today (old base) | 1440 | false | 0 | 0 | 0 | 0 |
| /today | 375 | false | 0 | 0 | 0 | 0 |
| /ledger (old base) | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | false | 387 (uncapped count) | 0 | 0 | 0 |
| /ledger after filter swap | 1440 / 375 | false | 0 / 387 | 0 | 0 | 0 |

HTTP >= 400 responses: 0 on every row, so rd/js/csrf.js and rd/js/htmx-csrf.js load (200).

## Checks

- /dev/shell: both script tags present; htmx.defineExtension available; `<body hx-ext="csrf">` still set. No state-changing HTMX request fires on the page, so the CSRF header was verified by reading htmx-csrf.js (registers the extension, attaches X-CSRF-Token on POST/PUT/PATCH/DELETE; GET carries none by design).
- /ledger (old JS): changing the date_from filter fires exactly one GET /ledger/table (hx-target #ledger-table, outerHTML); #ledger-table count is 1 after the swap, no new duplicate ids, no console error, no failed request. (A first run that dispatched the change event twice showed htmx:sendAbort console lines from hx-sync replace; that was the script's double trigger, not the app, and the clean rerun has 0.)
- Error summary: rendered through the app Jinja env (field_count=2) and injected into main on /dev/shell at 1440 and 375. role=alert, tabindex -1, id error-summary; links href `#field-amount` and `#field-category_id`; title "2 fields need attention"; no horizontal scroll introduced (width 1280 / 343, right edge within viewport). Looks right in both screenshots (red-bordered box, list with underlined links). Singular wording covered by tests/contract/test_dialogs.py.

## Step 3b

- error-summary.html: rg for style=, float, / 100, * 100, {% set: no matches. The only logic is the singular/plural ternary on field_count (wording, not money or dates); inputs come from web/field_labels.field_summary.
- Swap targets: /dev/shell has no hx-target; #ledger-table unique before and after swap. The 422 handler is the only new swap behaviour; its server side (HX-Retarget, HX-Reswap, summary, aria-invalid) is asserted by tests/contract/test_dialogs.py.
- Failing saves: no state-changing form on the audited pages and no route yet uses dialogs.py, so forced 404/409/500 is not applicable; to be audited with the first dialog route.
- Money formatting / rendered numbers: none on the touched templates (n/a).

## Findings

- None blocking. /ledger @ 375 overflowingElements is pre-existing (old ledger table inside an overflow-x:auto wrapper, horizontalScroll=false; same in the T-UR01 and T-UR02 audits); this change touches no old template or CSS.

Verdict: CLEAN.
