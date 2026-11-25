# Frontend visual audit: F2 Ledger handoff parity (2026-11-25)

Item F2 (branch `wi/ui/sourdough/F2`, audited at sha `ef38af4`), skill `frontend-visual-audit`
(Playwright, Chromium headless, scratch DB seeded by `tests/visual/handoff_seed.py` with the
`recurring-board` modifier, server clock frozen at 2026-10-31 via `tests.visual.frozen_server`;
never `data/budget.sqlite`). Screenshots are under
`/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/out/`
(ephemeral; not committed).

## Routes x viewports

Routes: `/ledger`, `/ledger?view=planned`, `/ledger?view=recurring` (all rows expanded as an extra state;
rows with overrides open expanded by default), `/ledger/recently-deleted`; plus the first row menu and each
dialog reachable from it (actual: edit; planned: promote, edit; recurring: promote, override, edit).
Viewports 1440, 1024, 375. horizontalScroll (page), duplicateIds, consoleErrors, requestFailures were 0 in
every row (46 captures). overflowingElements is the only non-zero signal:

| Route / state | 1440 | 1024 | 375 |
|---|---|---|---|
| /ledger (page, menu, edit dialog) | 0 | 0 | page 0, menu 0, edit dialog 2 (chip scroller) |
| /ledger?view=planned (page) | 0 | **10+ (actions column)** | 0 |
| planned menu, promote dialog | 0 | 0 | 0 |
| planned edit dialog | 0 | 0 | 2 (chip scroller) |
| /ledger?view=recurring (page) | 0 | **10+ (actions column)** | 0 |
| recurring all-expanded, menu, promote, override dialogs | 0 | 0 | 0 |
| recurring edit dialog | 0 | 0 | 2 (chip scroller) |
| /ledger/recently-deleted | 0 | 0 | 0 |

## Findings

1. **Layout, blocking (overflowingElements): planned and recurring tables at 1024.** The table is 960 px wide
   inside `.rd-table-scroll` (`overflow-x: auto`, 928 px wide, `src/budget_planner/web/static/rd/css/components/ledger.css:8`),
   so the actions cell (promote button, expand toggle, row menu; right edge 1058 > 1024) is clipped and only reachable
   by scrolling the table sideways. Page horizontalScroll stays false. In the recurring 1024 screenshot the row menus and
   expand toggles are not visible, and the second override panel of the two-column detail is cut at the right edge.
2. **Layout, blocking (visual): recurring detail at 375.** In the override list the month label ("Oct 2026") overlaps the
   amount ("15,800.00") in the expanded detail (all four rows of the Salary rule and the Taxes override row);
   the text runs together.
3. **Not a defect (listed for completeness): 375 edit dialogs** report `label.rd-chip-option` / `input` past the
   viewport. They sit in `.rd-catfield__recent` (`overflow-x: auto`), an intentional horizontal chip strip; the
   same count appears on the pre-existing `/ledger` transaction edit dialog.
4. **Reachability of /ledger/recently-deleted.** The only link is the `recently deleted →` aside in the pagination
   footer of the actual view (`fragments/ledger/actual-table.html:57` -> `pagination.html`). Planned and recurring
   views and empty states no longer link to it, and the page itself has no link in or out. Reachable only from
   `/ledger` (actual tab) or by URL.

## Step 3b (behaviour contract and template logic)

- Swap targets: `#modal-root` and `#ledger-table` match exactly one element on all four routes; every `#txn-*`
  and `#planned-p-*` target matches exactly one element. Recurring and recently-deleted pages have no others.
- No duplicate ids on any page or open dialog (0).
- Failing saves are visible (checked at 1440 on a scratch server, requests forced or real):
  - edit planned: real 422 for `1.2.3` ("amount must be a decimal number within range") and `0` ("Enter an amount above 0.00")
    in `.rd-dialog__hero-error`, dialog stays open; forced 500 gives the flash "Something went wrong on our side. Try again.", dialog stays open.
  - override: 422 for `0` and `1.2.3` shown in the hero error; forced 500 shows the error flash, dialog stays open.
  - promote (planned): 422 for `0` and `1.2.3`; forced 500 and 409 show the error flash ("That item changed in the meantime. Reload and try again."), dialog stays open.
  - Note: typing `abc` into the amount is sanitized client-side and saves the unchanged value (success flash); not a failing save.
- No arithmetic or `float`: `rg` for `float`, `/ 100`, `* 100`, `{% set` over the ledger fragments, pages, row, dialog and menu templates returned nothing.
- Rendered numbers: planned hero -1,531.35 PLN net equals the sum of the three rows (-2,239.80, -412.00, +1,120.45); row amounts match the seeded values
  (EUR-account tax refund shown as +1,120.45 PLN). No service-vs-page mismatch found; JPY not present in the handoff seed (not checked).
- Not exercised: delete/skip-next/restore actions (outside the requested dialogs).

Result: FINDINGS (items 1 and 2 blocking).
