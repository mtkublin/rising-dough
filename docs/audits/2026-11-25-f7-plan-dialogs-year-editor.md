# Frontend audit: F7 Plan dialogs and inline year-cell editor (2026-11-25)

Item F7 on branch wi/ui/sourdough/F7 at 3b00ade. Skill: frontend-visual-audit (Playwright, headless Chromium).
Scratch DB built by `tests/visual/handoff_seed.py` (not `data/budget.sqlite`), server through `tests.visual.frozen_server` with the clock frozen at 2026-10-31. Screenshots: `/tmp/claude-0/-home-user-rising-dough/bb5462da-5905-5890-a7d9-fc9c31189361/scratchpad/f7/shots/<desktop|tablet|mobile>__<state>.png` (desktop 1440, tablet 1024, mobile 375).

## Routes x viewports

Routes: `/plan?tab=year` (grid, editor open, invalid save dialog, Shift+click dialog, after save, forced 500/404/409), `/plan` (budget tab, row menu by pointer and keyboard, override dialog, tier saves, remove override confirm), period picker (month grid on `/plan`, year popover on `/plan?tab=year`).

| Route / state | 1440 | 1024 | 375 |
|---|---|---|---|
| year grid | hs=0 ov=0 dup=0 ce=0 rf=0 | hs=0 ov=20* dup=0 ce=0 rf=0 | hs=0 ov=20* dup=0 ce=0 rf=0 |
| year, editor open | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| year, invalid 1.2.3 -> override dialog | 0/0/0/ce=1**/0 | same | same |
| year, Shift+click dialog | 0/0/0/ce=1** (carried)/0 | same | same |
| year after one-off save | 0/0/0/0**/0 | ov=20* | ov=20* |
| budget tab | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| budget row menu, override dialog, remove confirm | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| period picker month grid | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| period picker year popover | 0/0/0/0/0 | ov=20* | ov=20* |

Columns: horizontalScroll, overflowingElements, duplicateIds, consoleErrors, requestFailures.

*  overflowingElements=20 (capped list) is the year table (`table.rd-year`, right edge 1198 at 1024 and 1182 at 375) inside `.rd-table-scroll.rd-year__scroll` (overflow-x: auto, scrollWidth 1150 vs clientWidth 311 at 375). It is a designed scroll container: horizontalScroll=false, page not widened. The F7 diff touches no CSS and no table markup, so it is not new. It was not re-measured on MAIN.
** The only console errors on plain loads are 0. The counted entries are the browser's "Failed to load resource" line for the deliberate 422 of the invalid save (one per viewport), and, on the budget rows, the three forced 500/404/409 responses injected with `page.route`. No JS exception, no pageerror, requestFailures=0 everywhere, no HTTP 4xx/5xx other than the intended ones.

## Behaviour checked (all three viewports unless noted)

- Plain click on a month cell opens `rd-year-editor`: the input is focused, holds the cell value (525.26), label "Nights Out, November budget".
- Enter saves a one-off: the cell shows `• 321.00`, no editor left, DB row `budget_one_off_overrides` amount 32100.
- Escape cancels, no editor left, the cell link is visible again and focused (aria-label read back).
- Invalid `1.2.3` + Enter: override dialog opens in #modal-root with the visible error "enter an amount of 0 or more"; at 375 the dialog is a bottom sheet (0,392, 375 wide).
- Shift+click opens the override dialog (tiers one-off, recurring, default; one-off checked).
- Keyboard only: Tab to a cell link, Enter opens the editor (input focused); Shift+Enter on the cell link opens the override dialog. That is how a keyboard user reaches the dialog; there is no other visible control for it in the editor (Tab from the input lands on the visually hidden submit button). Informational, see findings.
- Budget tab: row menu opens by click and by keyboard (Enter on the kebab focuses the "override" item), the dialog saves the three tiers (this month only, every month, new default) and the dialog closes; remove override shows its confirm control.
- Forced 500 / 404 / 409 on the editor save: a visible error banner appears ("Something went wrong on our side. Try again.", "That item was not found. It may have been removed.", "That item changed in the meantime. Reload and try again."), the editor stays open with the typed value, the cell is not shown as saved.

## Step 3b

- Templates (`git diff ui/sourdough...HEAD` of `web/templates`): no `float`, `/ 100`, `* 100`, `set` block, round filter, arithmetic or currency literal in added lines.
- `app-year-cell.js`: no parseFloat, Number, toFixed, Math or `*`, `/` on amounts; it only copies `data-amount` into the input and the server parses.
- Rendered equals service/DB: Nights Out default 525.26 = `budget_defaults` 52526; Nov one-off `• 321.00` = 32100; Oct `• 783.11` = 78311; Subscriptions Oct `• 592.57` = 59257.
- Swap targets: `#modal-root` single; no duplicate ids after open, 422 swap, save or reload (duplicateIds=0 in every row).
- Failing saves visible: yes (422 dialog error, 500/404/409 banner). Money by currency (JPY / non-PLN) not exercised; the F7 change adds no new money formatting (values come from `plan_year_view`).
- Result: ok.

## Findings (none blocking)

1. Editor input and year cell links are 40 px high (editor width 75.7 px at 375) and the input font-size is 11px: below the 44 px touch guideline; usable, no overflow. Consistent with the existing cell size.
2. A keyboard user can reach the dialog only through Shift+Enter on the cell link (no on-screen hint); the plain Enter opens the inline editor.
3. At 375 the row menu: after ArrowDown the focus moved to a "cancel" button (the sheet footer), not the single menu item; Enter on the kebab focuses "override" first, so the menu is operable.
4. At 375 the full-page screenshot shows the period picker popovers pinned at the top-left of the page instead of under the trigger (desktop anchors correctly). Likely a full-page screenshot artefact of the top layer; not changed by F7.

Status: no blocking diagnostic.
