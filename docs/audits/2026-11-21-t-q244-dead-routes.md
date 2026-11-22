# Frontend audit: T-Q244 dead routes removed

Change: T-Q244 (Q-050, ADR-0056 amendment 2026-11-21). Deleted routes: `POST /recurring/formula/preview`,
`GET /accounts/last-checked`, `GET /plan/analytics`, `POST /budget/recurring/{category_id}/{month}`,
`POST /recurring/batch/promote-due`, `POST /recurring/batch/undo`. Deleted partials:
`partials/recurring/_formula_preview.html`, `partials/accounts/_last_checked.html`. No template included
either partial (grep of `templates/` and `static/`), so no rendered page changes; the audit confirms the
routes that sit next to the removed ones still render clean.

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q244.sqlite` (never `data/budget.sqlite`), logged in through a minted session.

## Routes and diagnostics

Routes: `/today`, `/plan?tab=analytics`, `/plan?tab=budget`, `/accounts`, `/ledger?view=recurring`,
`/ledger?view=actual`; each at 1440, 1024 and 375 (18 route x viewport runs, all HTTP 200).

| Diagnostic | Result |
|---|---|
| horizontalScroll | false in all 18 runs |
| duplicateIds | 0 in all 18 runs |
| consoleErrors | 0 in all 18 runs |
| requestFailures | 0 in all 18 runs |
| overflowingElements | 0 at 1440. Non-zero only inside scrollable table containers: 1024 `/ledger?view=recurring` (70), 375 `/plan?tab=analytics` (71), `/ledger?view=recurring` (302), `/ledger?view=actual` (387). |

Triage: the overflow counts are descendants of table and card wrappers on pages this change does not touch
(they match the T-Q216 audit note); page-level scroll is false. The 375 `/plan?tab=analytics` screenshot shows
the Spend/Largest-items tables clipped at the right card edge; this is existing layout of the inline analytics
bundle (the tab renders it inline, not through the deleted fragment route) and is left to the ADR-0107
redesign, which replaces these templates.

## Step 3b

1. Swap targets: no `hx-target`/`hx-swap` line touched; no template or JS referenced a removed URL.
2. Failing saves: no state-changing form changed.
3. No template arithmetic added or touched.
4. Rendered equals service: unchanged pages; `/plan?tab=analytics` still renders the bundle (test
   `test_plan_tab_analytics_renders`).
5. Scratch data only: yes.

## Screenshots

`/tmp/fe-audit-tq244/{desktop,tablet,mobile}__*.png` (18 files). Viewed `mobile__plan_tab_analytics.png`: tab
bar, period selector, spend table, income-vs-expense chart and largest items all render (clipping as above).
