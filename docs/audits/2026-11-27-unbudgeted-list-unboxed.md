# Frontend audit: unbudgeted list unboxed (UNBOX)

Date: 2026-11-27. Item UNBOX, branch wi/ui/sourdough/UNBOX, audited sha 39f78f0f. Tasks T-UR90 (R24), T-UR91 (R25).
Run with the frontend-visual-audit skill (Playwright, Chromium) against a scratch copy of data/demo.sqlite (migrated, login user seeded; Takeaway budget removed so Taxes, Fixed Costs, Takeaway and Bank Fees #18 are unbudgeted), 127.0.0.1:8141. data/budget.sqlite untouched.

Change: overrides.css removes the `.rd-disclosure` outer box (border, radius, inline padding, background); budget-line.html drops the "no budget" text from the unbudgeted status cell; mobile card status cell left-aligned.

Routes: /plan?tab=budget&year=2026&month=11, /plan?tab=year&year=2026, each collapsed and expanded, 1440 / 1024 / 375, light and dark. Driver and JSON in the scratchpad (UNBOX/audit.py, out.txt).

## Diagnostics

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures. Identical in light and dark.

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| budget, collapsed | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| budget, expanded | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| year, collapsed | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year, expanded | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |

(a) table.rd-year and children inside the sideways-scrolling year grid (right edge 1198 at 1024, 1182 at 375); identical on MAIN per the PLANCAT audit (2026-11-27-plan-unbudgeted-list.md); page has no horizontal scroll. Pre-existing, not from this change.

## Behaviour

- Computed style of `details.rd-disclosure` on both tabs, collapsed and expanded, all six viewport/theme combinations: border 0, radius 0, padding-left 0, background transparent, no shadow; body border 0 and transparent; summary padding-left 0, cursor pointer. The list is flush with the page content edge (detLeft 104 / 48 / 32 = the table's left edge).
- Summary toggle: pointer cursor, keyboard focus gives a solid 2px outline (text colour, light and dark). The earlier box seen in unblurred screenshots is that focus ring, not the removed outer box; blurred screenshots show plain text "▾ 4 categories without a budget" with no frame.
- Status cell (budget tab, expanded): all four rows read exactly "set budget" with one button, no "no budget" text, at every viewport and theme. 1440/1024: button right of the status column; 375: button left-aligned at the card edge (x 32 = row left 32).
- Mobile (375) cards: chip, bar, "0.00 / –" and the left-aligned button stack tidily; no overlap. The fixed bottom nav overlaps the full-page screenshot at one spot (capture artifact of a fixed element).
- Year tab: collapsed/expanded heading and four chips without a frame, chips flow under the grid.

## Other uses of .rd-disclosure

rg over src: templates pages/plan/budget.html and pages/plan/year.html only (plus year-grid.css base rules, overrides.css, the bundle). No use in settings, ledger or dialogs, so no other page changes; the rule is scoped to those two disclosures. The pre-existing `.rd-disclosure--table` padding rules removed in the diff were only used by budget.html.

## Step 3b

1. Swap targets: #modal-root count 1 before and after the set-budget dialog swap.
2. Failing saves visible: POST /budget/rules/*/overrides forced to 404, 409, 500 from the open dialog (1440 light): dialog stays open with "That item was not found. It may have been removed.", "That item changed in the meantime. Reload and try again.", "Something went wrong on our side. Try again."
3. No arithmetic in templates: the added template lines contain no float, / 100, * 100 or set block (grep rc 1); the diff only removes the "no budget" text.
4. Money formatting: not touched.
5. Rendered numbers: unchanged by the diff; list shows 0.00 / – for the four unbudgeted categories (no November transactions in the scratch data).
6. Duplicate ids 0 before and after the swap; no HX-Trigger emitters or listeners added.
7. Scratch data only.

## Findings

None blocking. Observation (not blocking): with the box gone, the summary reads as plain text with a ▾ marker and the pointer cursor; its affordance is the marker and focus ring only.

## Screenshots

Viewed: budget expanded at 1440 light and 375 dark, year expanded at 1024 dark. Others captured. Directory: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/UNBOX/shots (<viewport>-<theme>__<route>-collapsed|collapsed-focused|expanded.png).
