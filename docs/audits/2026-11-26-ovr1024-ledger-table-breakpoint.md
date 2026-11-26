# Frontend visual audit: OVR1024 (planned/recurring table override limited to 768-1119 px)

Change: `rd/app/overrides.css` `.rd-ledger--sched` slim tracks now only in `@media (48rem <= width < 70rem)`; from 1120 px the vendored handoff layout applies. Audited at sha fa09a9a4 with the `frontend-visual-audit` skill (Playwright, chromium), handoff base seed on a scratch DB (`tests/visual/handoff_seed.py`, frozen date 2026-10-31), never `data/budget.sqlite`. Screenshots in `/tmp/ovr1024/` (scratch, not committed): `<view>_<width>_<scheme>.png` plus `_menu`, `_edit`, `_edit_fail`, `_promote`, `edit_422`.

Routes: `/ledger?view=planned`, `/ledger?view=recurring`, plus row menu, promote and edit-planned dialogs over the planned table.

## Diagnostics (per route x viewport)

horizontalScroll / overflowingElements (outside the table scroll wrapper) / duplicateIds / consoleErrors / requestFailures were 0 / 0 / 0 / 0 / 0 for every row below.

| Viewport | planned light | recurring light | table width in wrapper | actions cell |
|---|---|---|---|---|
| 1440 | 0/0/0/0/0 | 0/0/0/0/0 | 1232 in 1232, no wrapper scroll; tracks 110/363.75/218.25/160/150/150 | fully inside |
| 1280 | 0/0/0/0/0 | 0/0/0/0/0 | 1184 in 1184 | fully inside |
| 1120 | 0/0/0/0/0 | 0/0/0/0/0 | 1024 in 1024; tracks 110/214/160/160/150/150 | fully inside |
| 1100 | 0/0/0/0/0 | 0/0/0/0/0 | 1004 in 1004; tracks 110/227.5/136.5/150/150/150 (override) | fully inside |
| 1024 | 0/0/0/0/0 | 0/0/0/0/0 | 928 in 928 | fully inside |
| 768 | 0/0/0/0/0 | 0/0/0/0/0 | 900 in 672: wrapper scrolls sideways (by design, labelled region); page has no horizontal scroll | inside the scroll wrapper, reachable by scrolling |
| 375 | 0/0/0/0/0 | 0/0/0/0/0 | cards, 311 wide, unchanged | n/a |
| 1440 dark | 0/0/0/0/0 | 0/0/0/0/0 | as light | fully inside |
| 1024 dark | 0/0/0/0/0 | 0/0/0/0/0 | as light | fully inside |

Boundary 1100 -> 1120: the override drops out at 1120; widths of the flexible tracks change (227.5/136.5 -> 214/160) but nothing clips and no sideways scroll appears on either side. At 1440 the tracks are the vendored handoff tracks (no override applies; the markup/classes equal `docs/design/rising-dough-frontend/pages/ledger/planned.html` and `recurring.html`).

Viewed screenshots: planned 1440 (table, promote and kebab fully inside), planned 768 with row menu open (menu and promote reachable in the scrolled wrapper), recurring 1100 (expanded override rows, actions column intact), planned 1440 edit dialog with empty amount.

## Dialogs and menu

Row menu opens (`.rd-menu:popover-open` = 1) at 1440, 1100, 1024, 768 on both views. Promote dialog opens at 1440, 1100, 1024, 768. Edit-planned dialog opens at those widths.

## Step 3b

- Failing save, empty amount: browser validation tooltip "Please fill out this field." shown, dialog stays open. With validation bypassed (server path): HTTP 422 swap shows the inline field error "amount must be a decimal number within range", dialog stays open, no duplicate ids after the swap. Not forced: 404/409/500 (the change is CSS only; no template or HTMX file touched).
- Swap targets: `#ledger-table` / `#modal-root` unique; unchanged by this change.
- Templates: `rg` for `float`, `/ 100`, `* 100` over planned-table, recurring-table and planned-row: no hits; no template changed in this item (diff is `overrides.css` and `derived.md`).
- Rendered numbers (planned -1,531.35 net = -2,239.80 - 412.00 + 1,120.45) match the row amounts; service values unchanged by this item.

## Findings

None blocking. Note: at 768 the planned/recurring table (min-width 900) scrolls sideways inside its wrapper by design, so the actions column needs a sideways scroll there; no clipping, no page-level scroll.

Result: CLEAN.
