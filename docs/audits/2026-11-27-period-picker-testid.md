# Frontend audit: period-picker head test hook (CIFIX3)

Change: `data-testid="period-pick-head"` on the swapped head wrapper in `src/budget_planner/web/templates/fragments/popovers/period-picker.html`. No CSS or behaviour change.
Run: `frontend-visual-audit` skill, Playwright, scratch DB copy of `data/demo.sqlite` (migrated, login seeded), item worktree on :8101 vs MAIN (`ui/sourdough`) on :8102 with an identical DB copy.

## Routes x viewports (picker open)

| Route | 1440 | 1024 | 375 | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|---|---|
| /plan?tab=budget | ok | ok | ok | false x3 | 0 | 0 | 0 | 0 |
| /plan?tab=year | ok | ok | ok | false x3 | 0 @1440; 10 @1024 and 375 (see below) | 0 | 0 | 0 |

The 10 overflowing elements on the year tab are the `table.rd-year` and its head cells at 1024 and 375, inside a scroll container (horizontalScroll is false). Identical on MAIN with the same DB (10 and 10): pre-existing, unrelated to this change.

## Behaviour (budget tab, all three widths identical)

- Next/prev year arrow by mouse: year 2026 -> 2027 -> 2026, URL unchanged (no navigation), popover stays open.
- Keyboard Enter on next/prev arrow: year swaps in place, URL unchanged, `document.activeElement` stays on the arrow id (`period-budget-next-year` / `period-budget-prev-year`) after each swap; repeated Enter reaches 2025.
- `data-testid="period-pick-head"` count is exactly 1 after every swap (5 swaps per run); no duplicate ids.
- Month cell click navigates (`/plan?tab=budget&year=2025&month=1`).
- Year tab: the picker is the year list (no year arrows, so no head); a year cell click navigates (`/plan?tab=year&year=2025`).
- Pixel comparison at 1440 against MAIN (open picker on budget and year, budget after swaps): all three screenshots byte-identical in pixels (ImageChops bbox None).

## Step 3b

- Swap target `#period-budget` matches one element before and after each swap (duplicateIds empty; one picker root).
- No `float`, `/ 100`, `* 100`, `set` in the touched template (rg: 0 hits); the diff is the one attribute.
- No state-changing form or money value in the picker; failing-save and number-equality checks not applicable.
- HX-Trigger: none emitted by the picker requests.

## Screenshots (viewed: popover placement, arrows, grid, current month highlight)

`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/out/a_{1440,1024,375}_{budget,year}_{open,after}.png` (item), `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/outm/m_*` (MAIN).

## Findings

None for this change. Year-tab table overflow at 1024/375 is pre-existing on MAIN.
