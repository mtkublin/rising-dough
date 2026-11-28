# Frontend visual audit: T-UR03b category-picker direction label

Task: T-UR03 follow-up (docs/plans/ui-redesign/tasks.md), branch wi/ui/sourdough/UR03b at e8345bb9. ADR-0107, ADR-0150.
Run with the frontend-visual-audit skill method (Playwright, chromium); heavy lock /tmp/ui-redesign-heavy.lock held and released. Same method as docs/audits/2026-11-24-t-ur04a-shared-fragments.md.

## What was audited

Change: fragments/fields/category-picker.html prints `{{ c.direction | direction_label }}` ("↓ expense", "↑ income", "⇄ transit", "± adjustment") instead of the bare direction value.

Route (scratch page, no app route includes the fragment yet): the fragment in the open state, rendered through the app Jinja env with the contexts of tests/ui_map/test_rd_shared_fragments.py (expense, income, transit) plus one adjustment category (Reconciliation), into a page linking /static/rd/css/app.bundle.css. No database used.

## Diagnostics

| Page | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| category-picker (open) | 1440 | false | 0 | 0 | 0 | 0 |
| category-picker (open) | 1024 | false | 0 | 0 | 0 | 0 |
| category-picker (open) | 375 | false | 0 | 0 | 0 | 0 |

requestFailures includes HTTP >= 400 responses, so the css, fonts and sprite resolve.

## Direction column checks

- Rendered labels: "↓ expense", "↑ income", "↓ expense", "⇄ transit", "± adjustment".
- Font is Geist Mono (bundled); all four glyphs render, no tofu (viewed).
- No wrap: every label is one line (20px high, longest "± adjustment" 79px wide), option rows 44px high at all widths; label right edge is 12px inside the row at 1440, 1024 and 375.
- Compared with docs/design/rising-dough-frontend/pages/overlays/category-picker.html (board screenshot at 1440): same right-aligned muted mono label with arrow, highlighted row darker, same spacing. At 375 the sheet variant shows the same column.

Screenshots (viewed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR03b/open__1440.png, open__1024.png, open__375.png, board__1440.png, board__375.png.

## Step 3b

- rg over category-picker.html for `float`, `/ 100`, `* 100`, `{% set %}`, `style=`, `round`, currency literals: no hits. The label comes from the direction_label filter (web/view_models.py), not a template literal or branch.
- Rendered numbers: the only number is total_count from the service (5 in the scratch context, shown as "search all 5 categories").
- hx-target/hx-swap: none in this fragment. No form post, so no failing-save path.

## Findings

None.
