# T-UR41 frontend audit: T-Q316/T-Q317 flows re-run on the migrated templates (2026-11-26)

Task: T-UR41 (docs/plans/ui-redesign/tasks.md). Base `7bae62cf` (`ui/sourdough`), branch `wi/ui/sourdough/UR41`.
Re-run of `docs/audits/2026-11-23-t-q316-t-q317.md` (routes `/today`, `/settings/security`, `/settings/password`,
`/auth/sessions`) widened to every route in `tests/e2e/crawl_inventory.json`. No code changed.

## Method (frontend-visual-audit skill: Steps 2, 3, 3b)

- Scratch DB: copy of `data/demo.sqlite` + migrations + a seeded login (`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ur41.sqlite`); `data/budget.sqlite` untouched. uvicorn on 127.0.0.1:8741, `BUDGET_ENV=dev`.
- Playwright (Chromium), logged in through `/auth/login`; light and dark (`localStorage rd-theme`), 1440 / 1024 / 375.
  Diagnostics per row: `horizontalScroll`, `overflowingElements` (with the nearest clipping ancestor), `duplicateIds`,
  `consoleErrors` (console error + pageerror), `requestFailures` (requestfailed + any HTTP >= 400).
- Screenshots (full page) in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots/`, named `<theme>__<vp>__<route>.png`; viewport crops `crop_*_375_*.png`.
  Viewed: today 375 (light), ledger 375, settings 375, plan?tab=year 1024, new-entry dialog 375, Undo toast and result.

## Sweep

Routes: `/today`, `/accounts`, `/ledger`, `/ledger/recently-deleted`, `/plan`, `/plan?tab=year`, `/settings`
(categories), `/settings?tab=fx`, `/settings?tab=prefs`, `/settings?tab=categories`, `/settings/password` (redirects to
`/settings/security#password`), `/settings/security`, `/auth/sessions` (redirects to `/settings/security#sessions`),
`/settings/users` (admin session), `/does-not-exist` (HTML 404). 12 owner routes x 3 viewports x 2 themes = 72 rows;
admin/extra routes 5 x 3 x 2 (the admin dark 375 rows were not captured: login hit the rate limiter, 429; the light 375
rows cover the same markup).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today | 1440 / 1024 | false | 0 | 0 | 0 | 0 |
| /today | 375 | false | 1 (`pre.rd-hero__loaf`, triaged below) | 0 | 0 | 0 |
| /accounts | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /ledger | 1440 / 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | false | 1 (`a.rd-tabs__tab`, triaged below) | 0 | 0 | 0 |
| /ledger/recently-deleted | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /plan | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /plan?tab=year | 1440 | false | 0 | 0 | 0 | 0 |
| /plan?tab=year | 1024 / 375 | false | 30 (table inside `.rd-table-scroll`, overflow-x:auto) | 0 | 0 | 0 |
| /settings, /settings/security, /settings/password, /auth/sessions | 1440 / 1024 | false | 0 | 0 | 0 | 0 |
| /settings, /settings/security, /settings/password, /auth/sessions | 375 | false | 2 (`a.rd-tabs__tab`, in `.rd-tabs` overflow-x:auto) | 0 | 0 | 0 |
| /settings?tab=prefs, fx, categories (admin) | 1440 / 1024 | false | 0 | 0 | 0 | 0 |
| /settings?tab=prefs, fx, categories (admin) | 375 | false | 3 (tabs, same strip) | 0 | 0 | 0 |
| /settings/users (admin) | 1440 / 1024 / 375 | false | 0 / 0 / 3 (tabs) | 0 | 0 | 0 |
| /settings/users (owner, non-admin) | all | false | 0 | 0 | 1 (404) | 1 (404) |
| /does-not-exist | all | false | 0 | 0 | 1 (404) | 1 (404) |

Notes on the non-zero counts:

- The 404 rows are expected, not defects: `/settings/users` is admin-only and answers 404 to a non-admin
  (ADR-0073, `web/app.py`), and `/does-not-exist` is the HTML 404 page (T-UR41a). The browser logs the 404 as a console
  error. Both pages render the 404 view with no overflow. `/settings/preferences` is not a route (tab is `?tab=prefs`).
- `horizontalScroll` is false on every row, light and dark: no page scrolls sideways.
- Dark and light rows are identical in every count.

## Triage of the known 375 overflowing elements

| Element | Right edge | Clipped by | Verdict |
|---|---|---|---|
| `a.rd-tabs__tab` (ledger "recurring 27" 380; settings "preferences" 403, "security" 504) | 380 / 403 / 504 | `nav.rd-tabs` / `div.rd-tabs`, `overflow-x:auto` (scrollWidth 348 vs clientWidth 311 on ledger, 472 vs 311 on settings) | Clipped by design: a horizontal scroll strip of pills; every tab is reachable by scrolling. Screenshots `crop_ledger_375_top.png`, `crop_settings_375_top.png`: the last visible pill is cut at the card edge ("recurring", "prefe"), no overlap. Minor: no fade or edge hint that more tabs exist (settings hides 2 of 4 tabs, "security" fully off-screen). |
| `label.rd-chip-option` in the new-entry dialog | 377 | `div.rd-catfield__recent`, `overflow-x:auto` | Clipped by design: the recent-category chip row scrolls ("GROCERI" cut at the edge). `crop_newentry_375.png`: no overlap, dialog fits 375 without horizontal scroll. |
| `pre.rd-hero__loaf` on /today | 399 (hero right edge 359) | `section.rd-hero`, `overflow:hidden`, loaf `position:absolute` | Edge clip is by design (decorative ASCII loaf bleeds off the hero). Visible blemish at 375: the loaf's art runs through the caption "101 days until salary (7 mar)" (`crop_today_375_top.png`, around y=225-260), so the caption text and the art overlap. Decorative, text stays readable: minor. |
| `table.rd-year` and descendants on /plan?tab=year at 1024 and 375 | 1198 / 1182 | `div.rd-table-scroll`, `overflow-x:auto` | Clipped by design: the 12-month grid scrolls inside its container; at 1024 Oct-Dec need a scroll (`light__1024__plan_tab_year.png`, last column cut). Minor. |

## Step 3b (behaviour contract)

1. Swap targets: every selector `hx-target` on `/today`, `/ledger`, `/accounts`, `/plan`, `/plan?tab=year`,
   `/settings`, `/settings/security`, `/ledger/recently-deleted` is `#modal-root` and matches exactly 1 element.
2. Failing saves, forced 404, 409 and 500 (`page.route` fulfilling the POST): password form (`/settings/password`), new-entry
   save (dialog), promote all due (`/planned/batch/promote-due`, native confirm accepted), income anchor
   (`/budget/preferences/income-anchor`). Each shows a visible `rd-flash--error` / alert with the matching message
   ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side...") and the
   new-entry dialog stays open (screenshots `3b_password_500.png`, `3b_newentry_500.png`, `3b_promote_500.png`).
   The only console errors in the run are the forced 4xx/5xx responses.
3. No arithmetic in templates: `rg` over `src/budget_planner/web/templates` for `| float`, `/ 100`, `* 100`,
   `| round`, `| int`, arithmetic in `{% set %}` and in `{{ }}`: 0 hits.
4. Money by currency: PLN and a converted EUR account (Checking EUR, shown as -6,601.15 PLN base) render through the
   filters. No JPY account exists in the demo data, so a zero-decimal currency was not exercised on a page (not covered here).
5. Rendered number equals the service value: `compute_fortune` on the scratch DB gives net 3440267, assets 3689543,
   liabilities 249276 minor; `/today` and `/accounts` print 34,402.67, 36,895.43 and -2,492.76. Match.
6. Ids and listeners: 0 duplicate ids after each HTMX request (new-entry save failure, promote, delete, undo, skip).
   `HX-Trigger` events were not re-inventoried; the static HTMX-contract guards are not part of this run.
7. Scratch data only.

### T-Q316 / T-Q317 flows

- Undo (T-Q316): on `/ledger` at 1440, 1024 and 375, row menu > delete shows the toast, `undo` posts
  `/transactions/<id>/restore`; no console error, no failed request, no duplicate id. The new shell does not do a full
  page reload after Undo any more (a window marker survives); the list is refreshed by HTMX instead, and the row is back.
  The recurring "skip next" toast on `/today` has no Undo (`web/routers/recurring.py:359` sets no `undo_url`), so Undo
  there is not testable; this predates this audit and is noted for the owner of T-UR17.
- Passkey (T-Q317): on `/settings/security` the "add passkey" button is enabled (Chromium) at all viewports.
- Side effect: the forced-failure run on the new-entry dialog first saved 3 real rows (12.34 PLN, Travel) before the
  route intercept was fixed; scratch DB only.

## Findings

| # | Route @ width | Problem | Severity | Evidence | Likely file |
|---|---|---|---|---|---|
| 1 | /today @ 375 | `.rd-hero__loaf` art overlaps the caption "101 days until salary (7 mar)" and is cut at the hero edge | minor | `.../shots/crop_today_375_top.png` | `src/budget_planner/web/static/rd/css/components/hero.css` |
| 2 | /ledger, /settings* @ 375 | tab strip hides tabs with no fade or scroll hint (settings: "security" fully off-screen) | minor | `.../shots/crop_settings_375_top.png`, `crop_ledger_375_top.png` | `src/budget_planner/web/static/rd/css/components/segmented.css` (`.rd-tabs`) |
| 3 | /plan?tab=year @ 1024, 375 | year grid needs horizontal scroll inside its container (Oct-Dec off-screen at 1024) | minor | `.../shots/light__1024__plan_tab_year.png` | `src/budget_planner/web/static/rd/css/pages/plan.css` |

No blocker. The new-entry chip row (`label.rd-chip-option`), the tab strips and the year grid are scroll containers
by design; the loaf is clipped by design with the caption overlap logged as finding 1.
