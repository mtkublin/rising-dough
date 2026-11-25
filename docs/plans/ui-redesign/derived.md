# Sourdough Redesign — Derived Screens, Decisions and Deviations

> ADR-0107 §1 and §7. Filled in at T-UR00 (decisions), then by each surface task (derived screens and deviations).

## Open design questions (T-UR00)

| # | Question | Source | Decision | Date |
|---|---|---|---|---|
| 1 | Visible entry point for bulk selection, or keep the hidden checkbox column (Tab / `x`)? | handoff README §6.7 | As delivered: hidden checkbox column (Tab / `x`), no visible entry point (operator) | 2026-11-22 |
| 2 | Inline promote row variant, or the promote dialog only? | handoff README §6 "no board" | Dialog only; inline routes removed (ADR-0134 §5) | 2026-11-21 |
| 3 | `g o` (board) or `g t` for Today? | handoff README §5 | `g t`; handoff corrected by overlay rows, app templates use `g t` (operator; ADR-0147 §5) | 2026-11-22 |

## Parity gaps (from `../ui-test-harness/parity.md`, T-UT06)

> **Resolved 2026-11-21.** The designer answered all 16 gaps ([designer-change-request.md](designer-change-request.md)); the operator decided the product questions ([ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md)). The Edit user follow-up was answered too (ST17, kept).

| Feature / screen | Status | Decision | Date |
|---|---|---|---|
| SH13 Export | board now exists | `export` menu beside Ledger tabs, kept on phone (ADR-0134 §6; T-UR28) | 2026-11-21 |
| TD10 Net-worth card | board exists | parity row was wrong; per-account list dropped by the designer | 2026-11-21 |
| L11 Recurring strip | dropped | covered by the Recurring hero | 2026-11-21 |
| L18 Credit-limit hint | board now exists | line under account, pink warning, save allowed | 2026-11-21 |
| L23b Inline promote | dropped | dialog only; remove inline routes (T-UR24) | 2026-11-21 |
| ST10, ST15, ST18, ST19 | boards now exist | forced change, add user, reset, delete (ADR-0134 §10; T-UR20) | 2026-11-21 |
| SH12 Theme switch | app change | redesign release, default system (T-UR27) | 2026-11-21 |
| AU07 First-run | app change | `/setup` with one-time token (T-UR21, T-UR22) | 2026-11-21 |
| AU08, AU09, ST16 Invites | app change | invites beside direct add; email behind a switch after cost check (T-UR18..T-UR20) | 2026-11-21 |
| AU14 Offline | app change, partly deferred | save-failure path in release; service worker deferred (T-UR25, T-UR26) | 2026-11-21 |
| AC07 Account delete | app change | refuse while referenced (T-UR23) | 2026-11-21 |
| ST17 Edit user | board now exists | kept: name + member/admin, email read-only; first row-menu item; own row has no menu (ADR-0134 §11; T-UR20) | 2026-11-21 |

## Derived screens

| Screen | Surface task | Built from | Notes |
|---|---|---|---|
| _…_ | | | |

## Deviations from the handoff

| Where | Deviation | Reason | Task |
|---|---|---|---|
| Today, afford-invalid | The HTMX 422 body is the bare message (`Enter an amount, like 250.00`, pinned by `tests/integration/web/test_today.py`); it is retargeted into the result `<output>` (`HX-Retarget`), so the live state shows the text without the separate `.rd-field__error` line and `aria-invalid`. The full handoff state is the server render of `GET /today?amount=<invalid>` | contract and integration tests pin the 422 body; HTMX cannot add markup around a bare body | T-UR07 |
| Today, afford-over / afford-invalid page states | Reproducible as `GET /today?amount=1800.00` and `GET /today?amount=0` (new optional `amount` query on `/today`, also the no-script fallback of the afford form) | the visual harness needs a URL per state | T-UR07 |
| Today, loading | No skeleton in the app: during a range change or refresh the panel shows the `.htmx-request` progress line (`hx-indicator="#upcoming"`) | HTMX swaps whole responses; the skeleton fragment is kept for pages that render a placeholder first | T-UR07 |
| Today, upcoming row menu | `skip` on a planned row soft-deletes it (`POST /planned/{id}/delete`, restorable in Recently deleted); on a recurring row it is `skip-next`. `promote` and `override` open the existing (old-markup) dialogs in `#modal-root` until T-UR07b and T-UR10 port them | no planned-skip route exists; dialogs are other tasks | T-UR07 |
| Today, hero loaf at 375 px | The ASCII loaf overflows the hero at 375 px, exactly as in the handoff (visual-audit finding accepted as handoff parity) | handoff parity (ADR-0107 section 1) | T-UR07 |
| Today, hero bar | `aria-label` is `N percent spent, M percent left` with `M` = remaining over budgeted (committed excluded), so the two need not add to 100 | handoff data row 6 (value-inventory 5) | T-UR07 |
| Accounts row, sparkline | The polyline carries `transform="translate(0 2)"` and its points span a 24 px plot (y 0..24) instead of y 2..26 | Points come from `services.balance.sparkline_points` (canonical, no margin parameter); the 2 px margin of the chart notes is applied by the transform, identical pixels | T-UR08a |
| Accounts row, credit line | `data-testid="credit-utilisation"` on `.rd-account__credit`; bar `aria-label` is `bar_aria_label` (`49 percent spent, 51 percent left`), the handoff sample rounds the left cells (`80`) | UI-map locator for the line (last resort, ids are data); one aria wording across all bars (`view_models.bar_spans`) | T-UR08a |
| Accounts row, menu | Menu markup is inline in `rows/account-row` (items are `hx-get`/`hx-post` buttons to the existing routes), not the shared `menus/row-menu` fragment | The shared fragment only renders `href` links or `hx-post` items and has no phone-only item; UR08b swaps the items for the new dialog links and can then move to the shared fragment (needs `hx_get` and `phone` support) | T-UR08a |
| Accounts hero, empty state | The empty page prints the real totals (`0.00 PLN`, `0 accounts`, `assets 0.00 · liabilities 0.00 · planned 0.00`) | `accounts--empty.html` repeats the sample page's hero (`34,439.69 PLN`, 10 accounts) beside an empty list, which cannot be true; the empty route (`/accounts?state=empty` on the mockup target) is only a state of the same page | T-UR08a |
| Accounts "checked" | Prints the newest snapshot date (`01 APR`), or `never`; the old relative chips (today, N days ago, stale) are dropped | The handoff shows a date only | T-UR08a |
| Accounts planned note | `-> 3,662.52 after planned` (projected balance) replaces the old `-9,824.01 planned -> 2,575.99` sub-line | Handoff wording; the signed planned net stays in the hero (`planned -312.54`, id `accounts-planned-total`) | T-UR08a |
| `pages/plan/budget` period links | `?year=&month=` instead of the handoff's `?period=YYYY-MM` | contract tests and journeys pin the app's query names | T-UR11 |
| `pages/plan/budget` row menu, `override` item | link to the existing `GET /budget/rules/{id}/overrides/new` (with `hx-get` into `#modal-root`) | the override dialog is rebuilt by the second Plan item; the static board links to its overlay page | T-UR11 |
| `rows/budget-line` over-budget bar | `aria-label="over budget"` as in the handoff, clamped `used_pct` is not printed | `bar_spans` label would read "100 percent spent, 0 percent left" | T-UR11 |
| `pages/plan/forecast` horizon buttons | `button`s with `hx-get` of `/plan?tab=forecast&horizon=N`, `hx-select="#main"`, `hx-push-url`, plus `value="N"`; the whole `<main>` reloads so the hero and the note follow the horizon | the hero label, figure and note depend on the horizon; the handoff buttons are static | T-UR12 |
| `charts/forecast` month labels | Labels are thinned to every n-th month when neighbours would be closer than 40 px (n = 1 up to 24 months, 3 at 60); the tick marks stay | the board only draws 12 months | T-UR12 |
| `charts/forecast` single point | One month sits mid-plot; no points: the empty chart without line or dots | the board has 12 points | T-UR12 |
| `charts/income-vs-expense` more than four months | Every x measure (slot 116, loaf 34, band 108) shrinks by one factor so up to 12 months fit the 470 px plot; a loaf is never flatter than its radius plus the 4 px base; a zero amount draws no loaf | the board draws exactly four months | T-UR12 |
| `charts/income-vs-expense` months | Only months with income or expense activity in the trailing 12 are drawn (as the service returns them) | `analytics.income_vs_expense_monthly` is sparse | T-UR12 |
| `pages/plan/analytics` period links | `?year=&month=&period=month\|year\|trailing-12` instead of the handoff's `?period=YYYY-MM`; the range buttons are `hx-get` buttons that reload `#main` | contract tests and journeys pin the app's query names; the range already exists as `period` | T-UR12 |
| `pages/plan/analytics` picker note | The note names the window being summed (`oct = 1 oct -> 31 oct`, or `year to date = 1 jan -> 31 dec`) | the handoff note (`oct = 7 oct -> 7 nov`) is the budget income-to-income range; analytics sums calendar windows | T-UR12 |
| `rows/analytics-category` link and delta | The chip links to `/ledger?view=actual&category_id=..&date_from=..&date_to=..` (not `?category=Name`); a category without a 12-month average (or equal to it) prints `—` instead of a delta | the ledger filter takes ids; the board has a delta on every row | T-UR12 |
| `rows/analytics-category` bar | A non-zero amount always shows at least one of the 20 cells, while the label keeps the floored share (`0 percent of spend`) | handoff sample (Travel, Sport) | T-UR12 |
| `pages/plan/analytics` largest items | Name is the category, the link opens the ledger on that day; empty state `No expense transactions this period.` | `LargestItem` has no transaction link target in the ledger | T-UR12 |
| `/forecast`, `/forecast/view` | Still render the old markup (templates `forecast/index.html`, `partials/forecast/*`) | pinned by `tests/contract/test_plan_views.py`; T-UR15 retires the routes together with the contract rows | T-UR12 |
| Plan forecast and analytics, seed gap | The overlay geometry generator (`tests/visual/overlay.py` `geometry_rows`) is not wired into serving: the base seed gives a forecast peak of 58,761.15 (4 gridlines, 30k to 60k) where the board has 86,239.67 (5 gridlines, 20k to 100k), and one month of income and expense where the board draws four (Jul to Oct); an overlay cannot add elements | ADR-0147 section 3: the seed must carry the handoff data (seed change in `handoff_seed.py`) before chart rows can be generated | T-UR12 |
| `charts/forecast` scroll container | The plot `div.rd-chart-card__plot` carries `tabindex="0" role="region" aria-label="Chart (scrolls sideways)"` | handoff markup has none; keyboard access for the 375 sideways scroll | T-UR12 |

> **Transitional (T-UR08a, until T-UR08b):** the dialogs (new, edit, delete, reconcile) and their POST responses still render the old `partials/accounts/_card.html`, `_row.html` and the slide-over into the new page, so a swapped old row or slide-over looks unstyled until T-UR08b ports them. The row menu, the `reconcile` link and `+ new account` already target the existing routes with `#modal-root`.

## Tolerance exceptions

> Default is the strict visual tolerance: 0.1% differing pixels and the cluster cap `MAX_DIFF_CLUSTER_PX` (ADR-0106 amendment 2026-11-22, ADR-0147 §2). A surface may use a looser value only with a row here: reason plus operator sign-off, naming which limit is loosened. Data mismatches never justify an exception; they are overlay rows (below).

| Surface | Ratio / cluster cap | Reason | Operator sign-off | Task |
|---|---|---|---|---|
| _…_ | | | | |

## Handoff data overlay

> ADR-0147 §3–§4. Rows live in `tests/visual/handoff_overlay.toml` (T-UR00b); this section summarises why each group of rows exists. Text and value attributes only; the vendored handoff is never edited.

| Pages | What is corrected | Reason | Task |
|---|---|---|---|
| all pages with the nav and shortcuts dialog | `g o` → `g t` (`aria-keyshortcuts`, key labels) | operator decision, question 3 | T-UR00b |
| `overlays/delete-account*` | "Investments E" → an account in the seed | not in the handoff's account list (handoff README §6 item 17) | T-UR00b |

HTMX error flashes render the old partial's markup inside the new regions until T-UR15 (T-UR02, UR02b).
| Shell topbar | Shows the signed-in email before "sign out" (requirements section 6 / ADR-0075; handoff topbar has no identity slot; designer to confirm placement) | requirement wins on content | T-UR02 |
Today skip gives no toast, parity with the old page (it refetched the upcoming list; the new lists refetch on ledger-stale); undo toast is T-UR07b.
| Dialogs on 422 | Render `forms/error-summary` above the body (source fragment pages/errors/422.html:59; handoff overlays show inline errors only; designer to confirm) | covers fields with no inline slot and gives screen readers a list | T-UR04e |
