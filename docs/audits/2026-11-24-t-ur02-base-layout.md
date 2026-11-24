# Frontend visual audit: T-UR02 base layout (layouts/base.html) and /dev/shell

Date: 2026-11-24. Branch wi/ui/sourdough/UR02, commit 15f39831 (base f1815096). Task: T-UR02.

Change: new templates layouts/base.html, layouts/_palette.html, layouts/_shortcuts.html, fragments/flash/*, fragments/toast/undo.html, fragments/states/* (9), dev-only placeholder pages/dev/shell.html served by GET /dev/shell (router dev_components.py). No existing template or CSS changed (git diff name-status vs base: only additions plus the router).

Method: frontend-visual-audit skill (Playwright/Chromium, explicit viewports) against a scratch copy of data/demo.sqlite (migrated, password set on the copy), uvicorn on 127.0.0.1:8766, logged in through the real form. Screenshots in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/fe-audit/ (<viewport>__<route>.png). Viewed: desktop__dev_shell.png, mobile__dev_shell.png, desktop__dev_shell__dark.png, desktop__dev_shell__palette.png, desktop__dev_shell__shortcuts.png, mobile__dev_shell__systemdark.png.

## Results

| Route | Viewport | HTTP | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|---|
| /dev/shell | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 768 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 767 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell | 375 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell?view=theme | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell?view=theme | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /dev/shell?view=theme | 375 | 200 | false | 0 | 0 | 0 | 0 |
| /today (old base) | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /ledger (old base) | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /settings (old base) | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /today (old base) | 375 | 200 | false | 0 | 0 | 0 | 0 |
| /ledger (old base) | 375 | 200 | false | 20 | 0 | 0 | 0 |
| /settings (old base) | 375 | 200 | false | 0 | 0 | 0 | 0 |

HTTP >= 400 responses: 0 on every row (bundle CSS, sprite/favicon, all module JS load). Broken images: 0.

## Shell behaviour (1440 unless noted)

- Chrome follows the handoff (docs/design/rising-dough-frontend/pages/today.html): top bar with brand, rd-mainnav, new-entry button, help, settings, sign out; no side rail (the old base has the rail, the handoff does not). rd-mainnav is visible at 768 and above and rd-tabbar (5 cells, centre "+") is hidden; at 767 and below rd-tabbar is shown (grid, full width) and rd-mainnav is hidden. Switch confirmed at 768/767.
- Skip link: first Tab focuses "skip to content" (href #main, visible at top 8px); main#main exists, tabindex -1.
- Theme switch: light sets data-theme=light (bg rgb(255,255,255)), dark sets dark (bg rgb(13,13,11)), system removes the attribute; localStorage rd-theme persists. prefers-color-scheme dark on a fresh context renders dark (mobile__dev_shell__systemdark.png).
- Palette: Ctrl+K opens it; typing "led" filters to "Go to Ledger"; Enter navigates to /ledger.
- Shortcuts: "?" and the topbar "?" button open the dialog; g l -> /ledger, g t -> /today, n -> /transactions/new.
- Linked targets /today /ledger /plan /accounts /accounts/new /settings /transactions/new all 200.

## Step 3b

- Arithmetic / float / set in new templates: rg over all 15 added templates for float, / 100, * 100, {% set, style=, round and numeric operators: none (only hyphens in url_for paths and default('/path') URL defaults).
- Inline style: curl of rendered /dev/shell and /dev/shell?view=theme, grep -c 'style="' = 0 in both (ADR-0113).
- Assets and links: every href/src in the rendered page returns 200 (htmx, csrf.js, htmx-csrf.js, rd bundle CSS, favicon, 15 rd module scripts).
- Swap targets: page has no hx-target; #flash-region, #modal-root, #drawer-root, #toast-root each exist exactly once (duplicateIds 0). No forms save on /dev/shell (sign out is a plain POST form), so forced 404/409/500 not applicable. Money rendering: none on the page (n/a).
- Old pages unchanged: /today /ledger /settings render with the old rail and tab bar, same diagnostics as before.
- Step 3b: ok.

## Findings

- None blocking. /ledger @ 375: overflowingElements=20 (capped list; table.ledger right=650) with horizontalScroll=false (table sits in an overflow-x:auto wrapper). Pre-existing: identical in the T-UR01 audit, and this change touches no old template or CSS.
- Observations for the orchestrator (not blocking): (1) /dev/shell?view=theme renders the same page as /dev/shell (the router takes no view parameter; the page already contains the theme switch). (2) Today shortcut is "g t" in the templates while the handoff shows "g o" (documented in _shortcuts.html as ADR-0147 section 5; consistent across palette, cheatsheet and aria-keyshortcuts, and it works). (3) The fragments/states templates carry hard-coded URL defaults such as default('/transactions/new'); they are not rendered on /dev/shell, so not exercised here.

Verdict: CLEAN.
