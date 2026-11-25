# Frontend audit: T-UR15a old Budget and Forecast pages retired (redirects to the Plan hub)

Change: `/budget`, `/budget/yearly`, `/forecast`, `/forecast/view` now 307-redirect to `/plan?tab=budget&year&month`,
`/plan?tab=year&year`, `/plan?tab=forecast&horizon=<horizon_months>`; templates `budget/**`, `forecast/**`,
`partials/forecast/**` deleted; `pages/plan/forecast.html` got an `hx-get` refetch on `forecast-stale` and a
visually hidden table `<caption>`. Audited at `99db87a1` (MAIN `ui/sourdough`) with the `frontend-visual-audit` skill
(Playwright chromium, 1440/1024/375, redirects followed in the browser) on a migrated scratch copy of
`data/demo.sqlite` (never `data/budget.sqlite`). Screenshots in `/tmp/fe-audit-ur15a/` (viewed: 375 forecast
horizon 24, 1440 invalid-horizon 422 page, plus the per-route diagnostics for all rows).

## Routes x viewports (identical at 1440, 1024, 375 unless noted)

horizontalScroll=false, duplicateIds=0, requestFailures=0, `#main` count 1 on every row.

| Route (landed on) | Landed state | overflowingElements | consoleErrors |
|---|---|---|---|
| /budget (/plan?tab=budget) | budget tab, October 2026 | 0 | 0 |
| /budget?year=2026&month=10 (/plan?tab=budget&year=2026&month=10) | budget tab, October 2026 | 0 | 0 |
| /budget/yearly?year=2026 (/plan?tab=year&year=2026) | year tab, 2026 | 0 @1440; 20 @1024 and @375 (`table.rd-year`, inside `.rd-table-scroll` overflow-x:auto, 311/1150; no page scroll) | 0 |
| /forecast (/plan?tab=forecast) | forecast, 12 months | 0 @1440, @1024; 20 @375 (`svg` chart, inside `.rd-chart-card__plot` overflow-x:auto, 277/640) | 0 |
| /forecast?horizon_months=24 (/plan?tab=forecast&horizon=24) | 24 months, hero "end of sep 2028" | as above | 0 |
| /forecast/view (/plan?tab=forecast) | forecast, 12 months | as above | 0 |
| /plan?tab=forecast | chart + table, hero 27,490.12 PLN, horizon picker 6/12/24/60 with 12 current | as above | 0 |
| /plan?tab=budget, /plan?tab=year (regression glance) | unchanged | as above | 0 |
| /forecast?horizon_months=100000 (/plan?tab=forecast&horizon=100000) | 422 page | 0 | 1 (the browser's own "Failed to load resource 422" log for the document, expected) |

The non-zero overflowingElements are descendants of horizontal scroll containers that exist by design
(table region has `aria-label="Table (scrolls sideways)"`); none causes page scroll. The year tab and chart
CSS are untouched by this change.

## forecast-stale refetch (1440 and 375)

`htmx.trigger(document.body,'forecast-stale')` on /plan?tab=forecast: one GET `/plan?tab=forecast&horizon=12`,
`#main` replaced (outerHTML), `#main` count 1, duplicate ids 0, scrollY kept (400 -> 400), focus stays on body.
A second trigger refetches again (listener survives the swap). On `horizon=24` the refetch keeps horizon 24
(hero "end of sep 2028"). Not exercised through a real save (events are emitted by accounts, recurring,
transactions, planned routers; dispatched on body instead).

Caption: `<caption class="u-visually-hidden">Projected balance by month</caption>`, 1x1 px absolute, present in the
accessibility tree as the table name.

## Invalid horizon (new behaviour: 422 instead of clamp)

`/forecast?horizon_months=100000` -> 307 to `/plan?tab=forecast&horizon=100000` -> HTTP 422 full page
("422 · Can't save that · Rising Dough") inside the normal shell (nav intact). Body: "ERROR 422 / Can't save that /
Some fields need fixing. Your changes are still in the form. / 1 field needs attention / Horizon: horizon must be
one of 6, 12, 24, 60 / [ back to the form ]". So the error is visible and names the allowed values, but the copy is
wrong for a GET (there is no form, nothing is saved), "Horizon" links to `#field-horizon` which does not exist
on the page, and "[ back to the form ]" goes to `/today`, not to the forecast. Same 422 for `horizon=abc`, `-1`, `7`.
The horizon buttons only emit valid values, so only hand-edited or bookmarked URLs hit this.

## Step 3b

- Swap targets: forecast hero `hx-target="#main"`, `#main` is 1 before and after the swap. ok.
- Failing saves: this change adds no form; no state-changing request added. Not applicable.
- Arithmetic in `pages/plan/forecast.html`: `rg "float|/ ?100|\* ?100|{% set"` returns nothing. ok.
- Rendered numbers: hero and table values are the view-model values (27,490.12 PLN for 12 months, −6,949.57 change,
  peak 34,682.00 in aug 2027); no template computation; JPY not applicable (scratch data PLN only).
- IDs and listeners: `forecast-stale` has emitters (accounts, recurring, transactions, planned) and the new listener
  in `forecast.html`. Duplicate ids after swap 0. ok.

## Findings

1. Behavior/Content (triage): invalid-horizon 422 page copy and links are form-oriented (see above). Suggest a
   dedicated message for GET query errors, a back link to `/plan?tab=forecast`, and no `#field-horizon` anchor,
   or clamp as before. Operator decision.
2. No blocking diagnostics otherwise.
