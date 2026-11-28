# Frontend audit: picker chip leads on pointerdown (WEBKIT, static/rd/js/combobox.js)

Branch wi/ui/sourdough/WEBKIT @ 1948d7a9. Status: INCOMPLETE (BLOCKED, time budget exceeded).

## What ran
Scratch DB (migrated, seeded login user, 3 expense categories with recent entries), uvicorn in env=dev,
Playwright python driver (scratchpad audit.py) over `/ledger?view=actual` (new-entry dialog) and
`/recurring/<id>/edit`, at 1440, 1024, 375 (Chromium) plus one WebKit run at 1440.

Only the Chromium /ledger 1440 and 1024 rows completed (screenshots
`/tmp/fe-audit-webkit/chromium_1440_ledger.png`, `/tmp/fe-audit-webkit/chromium_1024_ledger.png`);
the script then hung on `/recurring/<id>/edit` and was killed, so its JSON results (the five
diagnostics, chip-move counts, keyboard checks) were never written.

## Not done (no evidence recorded)
- Diagnostics (horizontalScroll, overflowingElements, duplicateIds, consoleErrors, requestFailures): not captured.
- 375 viewport, edit-recurring picker, WebKit browser run, Step 3b: not run.
- Single-move / keyboard-selection checks: not captured.

## Findings
None confirmed. Possible finding: `/recurring/<id>/edit` as a direct GET did not complete in the driver
(may be fragment-only route; the dialog should be opened from /ledger?view=recurring instead).
