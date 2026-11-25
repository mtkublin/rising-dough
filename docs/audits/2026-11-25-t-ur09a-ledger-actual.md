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

---

# Visual-auditor run (2026-11-25, head e0198c67)

Skill run on a scratch copy of `data/demo.sqlite` (626 live actual rows, PLN plus a EUR account, transit rows, reconciliation rows, custom-colour
categories, 33 days, EUR to PLN rate 4.0 cached for 2026-11-19..25, one soft-deleted row) and an empty migrated DB (first run). `data/budget.sqlite`
untouched. Heavy lock `/tmp/ui-redesign-heavy.lock` taken and released. Screenshots under the session scratchpad `ur09a-audit/shots/` (viewed:
actual 1440 light and 375 dark, row menu 375 light, planned 375 dark, first-run 1024 light, recently-deleted 1440 light).

## Routes x viewports (1440, 1024, 375; light and dark = 6 captures per state, 66 captures)

States: `/ledger?view=actual` (populated), `&direction=expense&date_from=2026-10-01&date_to=2026-11-30` (filtered), `&q=zzzzqqq&date_from=2026-01-01&date_to=2026-01-31`
(no matches), `&page=2`, `&page_size=100` (long), row menu open, row selected with `x` (bulk bar, "1 selected"), `?view=planned`, `?view=recurring`,
`/ledger/recently-deleted`, and first run (empty DB).

| State | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| all `/ledger` states, all widths, both schemes | false | 0 | 0 | 0 | 0 |

Raw `overflowingElements` is 1 at 375 on every new-shell page: the last `.rd-tabs__tab` (right edge 380) inside `.rd-tabs`, a sideways scroller by
design (document `scrollWidth` is 375, no horizontal scroll); it is the scroller content, not an overflow. `/ledger/recently-deleted` reports 1 at
every width: the `sr-only` skip link at x = -9974 (offscreen by design). That page is still the old shell (sidebar, old table) and is not part of this item.

## Handoff comparison (actual, empty, no-matches, long, row menu)

Structure matches the boards (hero, tab pills with counts, export, filter bar with the phone `filters` collapse, day heading with NET, chips with the
custom colours, signed amounts with currency, row menu sheet on phone, bulk bar, empty state with loaf and two buttons). Differences are the derived.md
T-UR09 rows only. Planned and recurring (transitional): no horizontal scroll, the old table scrolls inside `.rd-table-scroll`, old kebab styling is
unstyled as derived.md says. At 1024 the shell top bar wraps to two rows and the filter selects truncate their placeholders (`all catego`); both are
shell/filter-bar sizing, not blocking (diagnostics 0), noted for the owner of the shell.

## Step 3b

- Templates (pages/ledger, fragments/ledger, rows/transaction-row, transaction-day): `rg` for `style=`, `{% set`, `float`, `/ 100`, `* 100`, `round`
  and arithmetic: no hits.
- Numbers: 24 Nov NET `+4,890.00` = 5,000.00 salary - 10.00 PLN - 25.00 EUR x 4.0 (converted); the EUR row prints `−25.00 EUR` in its own currency;
  25 Nov NET `−19.99`; 23 Nov NET `+14.72` (reconciliation keeps its stored sign, the transit row `⇄ 200.00` adds nothing). All equal the
  `actual_day_nets` / `signed_effect` values.
- Swap targets: every `hx-target` selector (`#ledger-table`, `#modal-root`, `#txn-*`) matches exactly one element; no duplicate ids after the filter
  swap, after the edit dialog open, or after delete.
- Edit: the row menu `edit` fills `#modal-root` with the OLD slide-over (`slide-over-root`, no `dialog[open]`). Expected: UR09b is not merged here.
- Delete: removes the row (no undo toast shown). Forced 500 on the delete: a visible error "Something went wrong on our side. Try again." appears
  and the row stays. One expected console 500 line for that forced request only.
- Filters: a filter change refetches `#ledger-table` and loads back from the URL (`?direction=expense&q=Cafe` restores both fields and the single row).

## Findings

1. Filter changes do not update the URL (`hx-push-url="false"` in `fragments/ledger/filter-bar.html:18`), so a reload after changing a filter drops it.
   Pagination links do carry the live filters (`...&direction=expense&page=2`). Behaviour as designed in derived.md ("filters keep working without
   script"); triage: accept or push the URL.
2. After a filter change the export links stay unfiltered (`/transactions/export?format=csv`), against derived.md "with the live filters". The export
   menu sits outside `#ledger-table` and is not refetched. Needs a fix by the implementer (or an amendment of the derived row).
3. Edit opens the old slide-over until UR09b (expected, recorded).
4. Delete shows no undo toast, only the removed row (accepted by the brief).
