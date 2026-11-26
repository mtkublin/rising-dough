# Frontend audit: month picker year arrows (PYEAR)

Date: 2026-11-26. Branch wi/ui/sourdough/PYEAR at 22431fad. Scratch DB (migrated, one login user), never data/budget.sqlite.
Change: the head prev/next-year arrows of `fragments/popovers/period-picker.html` hx-get the picker for pick_year=Y+-1 and swap only the popover; page URL and period stay; a month click navigates. Used by Plan · Budget and Plan · Analytics via `fragments/plan/period-nav.html`.

Run: skill `frontend-visual-audit` (its DIAGNOSTIC_JS from `scripts/audit_frontend.py`, Playwright Chromium, signed-in session), picker opened on each page. Light at all widths, dark at all widths. Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots/` (`<scheme>_<width>_<tab>_{closed,open,after_swaps,final}.png`); viewed: `light_375_budget_after_swaps.png`, `dark_1440_analytics_open.png`.

## Diagnostics (all 12 page x width x scheme combinations identical)

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /plan?tab=budget | 1440 | false | 0 | 0 | 0 | 0 |
| /plan?tab=budget | 1024 | false | 0 | 0 | 0 | 0 |
| /plan?tab=budget | 375 | false | 0 | 0 | 0 | 0 |
| /plan?tab=analytics | 1440 | false | 0 | 0 | 0 | 0 |
| /plan?tab=analytics | 1024 | false | 0 | 0 | 0 | 0 |
| /plan?tab=analytics | 375 | false | 0 | 0 | 0 | 0 |

Dark scheme: same six rows, all zero. Diagnostics were taken after the open, swap, month-click and Escape sequence. The popover bounding box lies inside the viewport in every row (including 375).

## Step 3b (behaviour contract)

Light, per route and width: open picker (2026), Next year -> 2027, Previous year -> 2026, Previous year -> 2025.
- Heading shows the expected year after each click; page URL unchanged; trigger label stays "November 2026"; popover stays open; no duplicate ids after each swap. Result: ok on both routes at 1440/1024/375.
- Month click (Mar, picker showing 2025) navigates to `/plan?tab=budget&year=2025&month=3` and `/plan?tab=analytics&period=month&year=2025&month=3`; trigger reads "March 2025". ok.
- Reopen, Escape closes (also checked after a swap at 375 via keyboard Enter on the arrow). ok.
- Swap target: `#period-budget` / `#period-analytics` each exist once before and after (duplicate-id check). ok.
- Template: the only added markup is hx attributes and hrefs from view-model URLs (`picker.prev_year_url`, `picker.next_year_url`, `picker.year`); no arithmetic, no float. ok.
- No state-changing form is added (GET swaps only), so the forced 404/409/500 save check does not apply. The year arrows keep real `href`s, so they degrade to full navigation without script.
- No money values rendered by this change; items 4 and 5 not applicable.

## Findings

1. A11y surface (minor): after an arrow click the swap replaces the clicked link, so `document.activeElement` becomes BODY (keyboard: focus focused the arrow, Enter, focus then lost; the popover stays open and Escape still closes it). A keyboard user must tab from the document start. Suggest keeping focus on the new arrow (e.g. `hx-on::after-swap` or the swap's `focus-scroll`/ id on the arrows restored by htmx `autofocus`/id preservation) in `period-picker.html`.
2. Cosmetic (not blocking): the note under the grid ("nov = 1 nov -> 1 dec") belongs to the page period and stays unchanged when browsing other years.

Verdict: no blocking diagnostics; one minor focus finding.
