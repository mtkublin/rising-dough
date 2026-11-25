# Frontend audit: F1 Plan surface handoff parity

Change: `budget-line.html` (a line without a budget renders its bar as a plain text run),
`plan_year_view.py` / `plan_data.py` (year row order, unset-cell rows, budget page lists a
category without a budget only if used). Audited at `3c2819d5` (branch wi/ui/sourdough/F1) on a scratch
DB built by `tests/visual/handoff_seed.py` (frozen 2026-10-31), never `data/budget.sqlite`, via the
`frontend-visual-audit` skill (Playwright, chromium headless shell, 1440/1024/375). Screenshots in
`/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/fe/` (viewed: desktop and mobile `/plan`, mobile `/plan?tab=year`, `err_year_cell.png`; the rest
captured, diagnostics read from `summary.json`).

## Routes x viewports

hs = horizontalScroll, ov = overflowingElements, dup = duplicateIds, ce = consoleErrors, rf = requestFailures (incl. HTTP >= 400).

| Route | Viewport | hs | ov | dup | ce | rf |
|---|---|---|---|---|---|---|
| /plan | 1440 | false | 0 | 0 | 0 | 0 |
| /plan | 1024 | false | 0 | 0 | 0 | 0 |
| /plan | 375 | false | 0 | 0 | 0 | 0 |
| /plan?tab=year | 1440 | false | 0 | 0 | 0 | 0 |
| /plan?tab=year | 1024 | false | 20 (rd-year table in its scroller) | 0 | 0 | 0 |
| /plan?tab=year | 375 | false | 20 (same) | 0 | 0 | 0 |
| /plan?tab=analytics | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /plan?tab=forecast | 1440 | false | 0 | 0 | 0 | 0 |
| /plan?tab=forecast | 1024 | false | 0 | 0 | 0 | 0 |
| /plan?tab=forecast | 375 | false | 20 (forecast svg in its scroller) | 0 | 0 | 0 |

The ov entries are contained: `table.rd-year` (1150 px) sits in `div.rd-table-scroll.rd-year__scroll`
(overflow-x auto, labelled region, tabindex 0) and `svg.rd-chart--forecast` (640 px) in
`div.rd-chart-card__plot` (overflow-x auto); no page scroll. F1 touches neither `year.html`, `forecast.html`
nor CSS, so these are pre-existing by construction (not re-run on MAIN). Triaged, not from this change.

## Screenshots checked

/plan 1440: no-budget rows (Bank Fees #18, Fixed Costs, Taxes) show a plain dotted bar, "0.00 / -",
"no budget"; only used categories listed. /plan 375: same rows stack cleanly. /plan?tab=year 375: grid
scrolls inside its region, unset cell dashed, "2 categories without a budget" disclosure present.

## Step 3b

- Swap targets: `#main` and `#modal-root` each match exactly 1 element on every route.
- Failing saves visible (budget override dialog `/budget/rules/7/overrides` and year-cell flow, opener
  `...overrides/new?year=2026&month=1&tier=one-off`): amount "abc" and "-5" give 422, dialog stays open with
  "enter an amount of 0 or more"; forced 404 / 409 / 500 (page.route) each keep the dialog open with a visible
  error ("not found", "changed in the meantime", "Something went wrong"). Empty amount returns 200 and clears the
  override (existing behaviour of parse_override, flash "budget saved"); noted, not a silent failure of an invalid value.
- Template logic: `rg` for float, / 100, * 100, set blocks in budget-line.html, pages/plan/*.html and
  year-grid-row.html: none. The only template diff is the `has_budget` branch.
- Rendered numbers: Total 6,449.08 budget, 5,014.55 spent, left 987.93 equals hero 987.93; row "left" values equal
  budget minus spent (604.35 - 234.82 = 369.53); values come from the view model. Not recomputed in templates.
- Duplicate ids after the dialog swap: 0 (both flows). Money filters: PLN scratch only (no JPY account in the
  handoff seed; not exercised).

## Findings

None blocking. Note: my invalid-input probes with an empty amount saved a 0.00 one-off for Big Purchases
Jan and Oct in the scratch DB only.
