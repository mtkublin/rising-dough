# Frontend audit: T-UR02e offline banner alone outside forms (Q29)

Change: `src/budget_planner/web/static/rd/js/app-toast.js` (`htmx:sendError` handler defers the
assertive "Could not reach the server" flash and skips it when `offline.js` put the offline banner
in `#flash-region`), e2e `tests/e2e/test_htmx_error_flash.py`. No template or CSS change.
Audited at `fd1956bc` (base `ui/sourdough` df6545c1) on a scratch copy of `data/demo.sqlite`
(never `data/budget.sqlite`), via the `frontend-visual-audit` skill (Playwright, chromium, 1440/1024/375).
Screenshots in `/tmp/fe-audit/` (viewed: `desktop_ledger_offline.png`, `mobile_ledger_dialog_offline.png`,
plus the per-viewport page shots).

## Routes x viewports (diagnostics, page loaded online)

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today | 1440 | false | 0 | 0 | 0 | 0 |
| /today | 1024 | false | 0 | 0 | 0 | 0 |
| /today | 375 | false | 1 (`pre.rd-hero__loaf`, decorative, clipped; no page scroll) | 0 | 0 | 0 |
| /ledger | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | false | 1 (`a.rd-tabs__tab`, tab strip scrolls inside its container) | 0 | 0 | 0 |
| /ledger + new-entry dialog | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger + new-entry dialog | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger + new-entry dialog | 375 | false | 2 (`a.rd-tabs__tab`, `label.rd-chip-option` in the horizontally scrolling chip row) | 0 | 0 | 0 |

The three mobile overflowingElements entries are not from this change (it touches one JS file and
no CSS/template; `git diff df6545c1 -- templates css` is empty) and none causes horizontal page
scroll. They sit in scroll containers by design. Not re-run on MAIN; reported to the orchestrator.

## Offline states

(a) Outside a form, offline (`context.set_offline(true)`):
- /today "7 days" upcoming button (hx-get, no form): 1440, 1024, 375 each show the offline banner
  in `#flash-region` ("You're offline ... retry now"), `#flash-region-assertive` empty. 3/3 ok.
- /ledger "[ new entry ]" link (hx-get to `/add`): 1440 and 1024 banner alone, assertive empty.
  At 375 the link is hidden by the layout; no outside-form trigger exists there (not applicable).
- Duplicate ids after the failed request: 0.

(b) Inside a form, offline (new-entry dialog, amount 12.50, save): at 1440, 1024 and 375 the offline
state appears inside the form (`#modal-root form [data-js="offline-state"]` = 1), none in
`#flash-region`, assertive flash empty; typed value kept. Unchanged from UR02d. At 375 the dialog was
opened via `htmx.ajax` to the same endpoint because the trigger link is hidden.
Console messages during the offline step (`htmx:sendError`, `ERR_INTERNET_DISCONNECTED`) are induced
by the deliberately dropped network, not by page load; they are not counted above.

## Step 3b

- Swap targets: /today `#afford-result`, `#upcoming-list`, `#modal-root` each match 1 element;
  /ledger `#modal-root`, `#ledger-table`, per-row `#txn-*` each 1; `#upcoming-list` still 1 and no
  duplicate ids after a swap.
- Failing saves visible: offline save shows the in-form offline state (b); 404/409/500 paths not
  touched by this change.
- No arithmetic/float in templates: no template changed.
- Rendered numbers: no number-rendering code changed (ledger hero 19,417.18 PLN unchanged path).
- HX-Trigger listeners: change is a listener on `htmx:sendError` only; no new emitter.

Findings: none attributable to T-UR02e.
