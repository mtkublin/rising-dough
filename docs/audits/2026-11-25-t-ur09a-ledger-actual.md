# Frontend visual audit (probe): T-UR09a Ledger, actual view

Task: T-UR09 part 1 (UR09a), branch wi/ui/sourdough/UR09a. ADR-0107, ADR-0123, ADR-0152. A visual-auditor runs after this probe.
Method: Playwright (chromium) probe against two scratch databases: a copy of `data/demo.sqlite` (616 actual, 1 planned, 27 recurring) and an empty
migrated one (first-run state). `data/budget.sqlite` not touched. Heavy lock `/tmp/ui-redesign-heavy.lock` taken around each run.

## Routes and states

`/ledger`: actual (normal), long (`page_size=100`), no matches (`q=zzzzqqq&date_from=2026-01-01&date_to=2026-01-31`), filter open (phone: the
`filters` toggle expanded), filter applied (direction `expense` through the select, table refetched), row menu open (first row), bulk select (first
row selected with `x`: the bar shows `1 selected`), plus `/ledger?view=planned` and `?view=recurring` (transitional, old rows in the new page), and
the empty DB (first run). 10 states x 3 widths (1440, 1024, 375) x light and dark = 60 captures.

## Diagnostics

| Group | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| all 60 captures (after the fix below) | false | 0 | 0 | 0 | 0 |

Overflow is measured outside the sideways scrollers (`.rd-table-scroll`, `.rd-tabs`, popovers), which scroll by design (handoff parity).
One finding fixed during the probe: planned and recurring at 375 had a document-wide horizontal scroll (the old `table.ledger` sat in the unstyled
`.ledger-scroll`). `ledger/_table.html` now wraps the old table in `.rd-table-scroll` (a labelled, focusable region), as the handoff does.

## Comparison with the handoff boards (actual, actual--empty, actual--no-matches, actual--long, row-menu--transaction)

Screenshots at 1440 and 375, light and dark, compared with the board structure: hero "spent this period" (peach light, orange dark), tab pills with
counts, export menu, filter bar (extra fields collapse behind `filters` on phone), day heading with `NET`, rows (description + account, chip,
signed amount with the currency, row menu), bulk bar over the table with the select column shown (header checkbox indeterminate), row menu with
`edit` / `delete`, empty state (loaf, `No entries yet.`, `[ new entry ]`, `new account`), phone tab bar. They match in structure and type.

Accepted differences are in derived.md (rows tagged T-UR09): filter query names, bulk actions disabled, no page-level "+ new entry", pagination
as links, the `recently deleted` link under empty states, the transitional planned and recurring views, the edit item until T-UR09b.

## Step 3b (behaviour contract and template logic)

- Templates (pages/ledger/index, fragments/ledger/*, fragments/rows/transaction-*): `rg` for `style=`, `{% set`, `float`, `/ 100`, `* 100` and
  arithmetic: no hits. Day labels, nets, amounts, chip hues, menu items, pagination links and the no-matches text are `web/ledger_view.py` values.
- Rendered numbers equal the service values: the day net comes from `services.ledger_totals.actual_day_nets` (exact values pinned in
  `tests/integration/web/test_ledger_actual.py`: `NET −110.00` for a PLN 10.00 expense plus a EUR 25.00 expense at 4.0; `NET +500.00`), the hero from
  `period_spent_minor`, row amounts from `format_figure` in the account currency (`−25.00 EUR`), U+2212 from `domain.money`.
- Swap targets: `#ledger-table` (filters, `ledger-stale`) and `#modal-root` (row menu `edit`, top-bar new entry) each match one element.
- A failing filter value (`page=x`, unknown `view`) is a 422 from the existing parsers (contract unchanged). Delete asks `hx-confirm`, answers the
  `ledger-stale` event; the table region refetches with the live filters (e2e `test_ledger_filters`).
- A saved new entry on the ledger closes the dialog: `rd/js/app-ledger.js` closes the open `#modal-root` dialog on `ledger-stale`.

## Findings

1. Planned and recurring rows still use the old kebab and slide-overs, which need scripts the new shell does not load (T-UR10a). Skipped e2e name it.
2. The edit item opens the old slide-over until T-UR09b (e2e skipped with that reason).
3. `form_responses.created_txn_response` leaves a new-entry dialog open on `/ledger` (reswap none, no `dialog-close`): handled on the page by
   `app-ledger.js`; the server-side fix (send `Event.DIALOG_CLOSE`) belongs to the owner of `form_responses.py`.
