# Frontend visual audit: T-UR01 vendored redesign assets (static/rd/)

Date: 2026-11-24. Branch wi/ui/sourdough/UR01, commit 77fa5b77 (base 2baf9786). Task: T-UR01.

Change: vendors the handoff under src/budget_planner/web/static/rd/** (plus generated rd/css/app.bundle.css), scripts/build_css_bundle.py, justfile css, two pre-commit hooks. No template or existing CSS changed; no template links rd/ yet. Audit goal: old pages render unchanged.

Method: frontend-visual-audit skill (Playwright/Chromium, explicit viewports) against a scratch copy of data/demo.sqlite (migrated, password set on the copy), uvicorn on 127.0.0.1:8765, logged in through the real form. Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/fe-audit/<viewport>__<route>.png (desktop=1440, tablet=1024, mobile=375). I viewed mobile__ledger.png: old layout intact, bottom tab bar and ledger table render as before.

## Results

| Route | Viewport | HTTP | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|---|
| /today | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /accounts | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /ledger | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /plan | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /settings | 1440 | 200 | false | 0 | 0 | 0 | 0 |
| /today | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /accounts | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /ledger | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /plan | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /settings | 1024 | 200 | false | 0 | 0 | 0 | 0 |
| /today | 375 | 200 | false | 0 | 0 | 0 | 0 |
| /accounts | 375 | 200 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | 200 | false | 20 | 0 | 0 | 0 |
| /plan | 375 | 200 | false | 20 | 0 | 0 | 0 |
| /settings | 375 | 200 | false | 0 | 0 | 0 | 0 |

Broken images: 0 on every row.

## Findings

- /ledger @ 375 and /plan @ 375: overflowingElements=20 (capped list; table.ledger right=650, table.rd-table right=724). horizontalScroll=false: the tables sit in an existing overflow-x:auto wrapper (rising-dough.css), so the page does not scroll sideways. Not caused by this item: the diff vs BASE touches only static/rd/**, scripts, justfile, pre-commit and tests, no template and no non-rd CSS, and nothing links rd/, so the old pages cannot differ from BASE. Triaged as pre-existing (by diff reasoning; BASE not re-rendered).
- All other rows: 0 on all five diagnostics.

## Step 3b (behaviour contract)

git diff --stat 2baf9786 -- src/budget_planner/web/templates is empty: no template changed, so no swap targets, forms, arithmetic or rendered numbers were touched. rg finds no static/rd reference in templates. Step 3b: ok (n/a, nothing in scope).

## Static asset serving (for T-UR02)

- GET /static/rd/css/app.bundle.css -> 200
- GET /static/rd/js/theme.js -> 200

Verdict: CLEAN for this change (one pre-existing mobile table overflow noted).
