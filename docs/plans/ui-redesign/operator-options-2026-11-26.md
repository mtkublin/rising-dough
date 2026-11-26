# Operator options, 2026-11-26: what blocks green handoff comparisons (T-UR00b, item P1)

Status: prepared for the operator. **Nothing here is applied to the app, the tests or the overlay.** Every option below was applied temporarily in a scratch worktree on base `d4c06a8` (head of `ui/sourdough`), measured with the local lab, then reverted. The exact minimal diff of each option is a unified diff in `docs/plans/ui-redesign/operator-options/<id>-<option>.patch` (`git apply --check` passes on `d4c06a8`; apply to a work branch, never to this one).

Sources: [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md) (design-parity group: "follow the handoff wherever the app differs"), [derived.md](derived.md) (rows marked operator or open), [ADR-0147](../../adr/0147-handoff-parity-ci-rendered-references-and-data-overlay.md) (§3 seed, §4 overlay: "the handoff side is corrected, never the app's logic"), [ADR-0151](../../adr/0151-designer-followup-answers-2026-11-23.md), [ADR-0089](../../adr/0089-accounts-planned-net-per-account.md), [ADR-0105](../../adr/0105-committed-includes-all-overdue-items.md).

## How to read the numbers

- **Lab**: the local copy of the CI comparison (`handoff.compare` with the overlaid handoff on one side and the app on the handoff seed at 2026-10-31 on the other; chromium 1243 with the `handoff.CHROMIUM_ARGS`; same recipes as `test_reference.py`). One scratch DB per page, never `data/budget.sqlite`.
- **Gate** (ADR-0147 §2): a page passes when the differing pixels are at most **0.1 %** and the largest 8-connected differing region is at most **52 px**, and the image sizes are equal. A size difference always fails.
- Cells read `ratio / largest cluster px`; `ok` = passes, `FAIL` = over a limit, `SIZE a%` = different image heights (ratio is then the shared window plus the missing area; the cluster is not computed).
- Shards: **1440L** = 1440 wide, light; **1024D** = 1024 wide, dark; **375L** = 375 wide, light. The other three shards were not measured; the differences found here are layout or text, so they repeat there.
- "Blocks" = the pages that cannot pass at the three measured shards while the decision is open.
- A **recommendation** is my judgement as the preparing agent, not a decision.

## Baseline on `d4c06a8` (all pages this document touches)

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| category-picker | baseline | FAIL 3.333%/19457 | FAIL 2.753%/-1 | FAIL 3.614%/2731 |
| category-picker--no-match | baseline | FAIL 2.653%/16978 | FAIL 2.811%/6570 | FAIL 1.327%/2299 |
| plan_budget | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| accounts--empty | baseline | FAIL 1.973%/11703 | FAIL 3.251%/11703 | FAIL 21.538%/26933 |
| today--afford-invalid | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--afford-over | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--flash | baseline | SIZE 8.76% | SIZE 10.86% | SIZE 13.75% |
| today--empty | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--happened | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--planned | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--repeats-fixed | baseline | ok 0.000%/0 | FAIL 7.343%/37290 | FAIL 3.164%/1511 |
| new-entry--repeats-formula | baseline | FAIL 0.164%/1878 | FAIL 0.107%/1116 | FAIL 0.065%/504 |
| new-entry--phone-sheet | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| accounts | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| delete-account | baseline | SIZE 10.47% | SIZE 11.65% | SIZE 12.89% |
| delete-account--blocked | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| delete-account--blocked-planned | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account--error | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account--filled | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| edit-account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| edit-account--liability | baseline | FAIL 12.480%/109118 | SIZE 21.32% | FAIL 22.473%/77367 |
| row-menu--account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| reconcile | baseline | FAIL 13.009%/94119 | SIZE 22.51% | FAIL 26.510%/59334 |
| reconcile--liability | baseline | FAIL 12.356%/89512 | SIZE 21.27% | FAIL 23.246%/40769 |
| auth_force-password | baseline | FAIL 3.709%/24990 | FAIL 6.061%/24760 | FAIL 11.618%/14716 |
| auth_force-password--error | baseline | FAIL 3.339%/17224 | FAIL 5.457%/17121 | FAIL 12.529%/14716 |
| one-time-password | baseline | FAIL 0.145%/117 | FAIL 0.241%/119 | FAIL 0.591%/212 |
| reset-password | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-category | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-category--filled | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-category--error | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| edit-category | baseline | FAIL 0.085%/1847 | FAIL 0.118%/1839 | FAIL 0.261%/1909 |
| today--loading | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| plan_forecast | baseline | ok 0.000%/0 | ok 0.001%/9 | ok 0.000%/0 |

Two findings outside the decision list, found while measuring (not blocked by any decision below, listed so they are not lost):

- `new-entry--repeats-fixed` fails at 1024D (7.34 % / 37,290 px) and 375L (3.16 % / 1,511 px) although it passes at 1440L: the dialog is taller than the 768 px / 812 px viewport and the diff shows the dialog body offset by about 70 px at 1024D (a scroll or position difference). `new-entry--repeats-formula` fails everywhere by a small cluster (0.164 % / 1,878 px at 1440L, 0.107 % / 1,116 px at 1024D, 0.065 % / 504 px at 375L).
- `new-account--error` at 1024D after D6-A shows a 2.57 % / 4,266 px difference that the 10 px height difference hid before (see D6).

## Summary

| Decision | Pages blocked (x shards) | Options (patch ids) | Measured (1440L / 1024D / 375L) | Recommendation (mine) |
|---|---|---|---|---|
| **D1** search all N, picker list | `category-picker`, `category-picker--no-match` (x3) | a `placeholder` overlay row; b keep the amount underline while the picker is open (CSS); c list = handoff's visible rows (archive modifier or overlay row op); d exception | a+b: `--no-match` green at 3 shards; `category-picker` 3.33 % to 0.86 % / 2,731 px; a+b+c (proxy): `category-picker` green 1440L and 375L, 1024D pixels 0.025 % (harness RGBA/RGB quirk) | a + b + c(i) |
| **D2** Q4 budget-row bar labels | none: `plan/budget` passes at 3 shards | a nothing; b six `aria-label` overlay rows | b: still green 0.000 % at 3 shards | b (no code) |
| **D3** Q5 `accounts--empty` | `accounts--empty` (x3) | a overlay rows (hero, caption); b app shows a hero with no accounts (impossible); c leave | a: green at 3 shards (was 1.97 %, 3.25 %, 21.5 %) | a |
| **D4** afford-it states | none: all pass at 3 shards today | a keep (13 seed-value rows); b ADR-0151 figure by overlay (not viable); c amend ADR-0105 (committed from today) | c: Today pages (5) green at 3 shards; `plan/budget` green once its two note rows keep the 6 to 8 categories-over change; `plan/forecast` red 0.018 % / 125 px (1440L), 0.028 % / 132 px (1024D): geometry rows to regenerate | a |
| **D5** typed values over tab switch | none (the harness never switches tabs) | a keep; b carry the form's values on the tab link | b: no pixel change; probe: amount, category, account, note survive all tab switches | b |
| **D6** ADR-0089 overdue in "after planned" | 8 accounts pages (x2: 1440L, 1024D) + the 4 of D8 | A count only items after today; B keep | A: 7 of 8 green at 3 shards (was 0.088 % / 132 px, SIZE at 1024D); `new-account--error` at 1024D then shows a separate focus-ring difference (2.57 %); removes 2 overlay rows | A (cost: overdue bills leave the projection) |
| **D7** force-password (+ `--error`) | both pages (x3) | a template + 2 rows (email, copy); b service: forced rotation skips the current password | a: `force-password` green at 3 shards (was 3.7 % to 11.6 %); `--error` green at 3 shards with the copy row (at most 0.098 % / 14 px) | a + b (security call is yours) |
| **D8** accounts dialogs | `edit-account--liability`, `reconcile`, `reconcile--liability`, `delete-account` (x3); `new-account` `as of` blocks nothing | L optional credit limit, card only; R reconcile extras out; E element-insert overlay op; T `as of` migration | L: green at 3 shards (was 12.4 % / 109,118 px); R: `reconcile` 13 % to 0.34 % / 4,665 px, `--liability` 12.4 % to 7.4 %; E proxy: `delete-account` green at 3 shards (was SIZE) | L + E now; R with a live hero + snapshot seed |
| **D9** `today--flash` 8 px | `today--flash` (x3, size) | A one `#flash-region`; B vendored CSS (violates Q8) | A: green at 3 shards | A |
| **D10** one-time password | `one-time-password` (x3) | A token port in the visual server; B 4-4-4 generator | A: green at 3 shards (was 0.145 % to 0.591 %) | A |
| **D11** swatch Takeaway | `edit-category` (x3) | S snap to nearest swatch; O overlay `data-color`; X recolour; T exception | S: green at 3 shards; O: 0.017 % / 447 px (ring remains) | S |


Reading guide for the table: "pages blocked" are the comparison pages that cannot pass while the decision is open (shards: 1440 light, 1024 dark, 375 light). "Measured" is what the option did in the lab; the per-option tables follow in each section. The recommendation column is my judgement, not a decision.

## D1. "search all N categories" and the picker list (pages `category-picker`, `category-picker--no-match`)

**What differs.**

- Handoff: the picker panel and the button both say `search all 21 categories` (38 occurrences in 19 files; none says 23 or 24). Its list has **21** options: 16 expense, 3 income (Salary, Side Income, VAT Refund), Transit, Reconciliation. So its 21 counts Reconciliation; the list starts at `Big Purchases` (highlighted).
- ADR-0151 §2 (designer-confirmed): Reconciliation is system-only, not in the picker and not in N; the overlay row (`value-inventory 5 row 12`) already rewrites the button to `search all 24 categories`. The ADR gives no number; the "23" sometimes quoted for this panel is not a picker count (it is Today's `showing 6 of 23`).
- App and seed: **24** options = the handoff's 20 non-Reconciliation entries plus **four the handoff list lacks**: `Bank Fees #18`, `Opłaty bankowe i prowizje`, `Interest`, `Profit Share`. All four are live categories the seed needs elsewhere (Today's upcoming row, the budget, the settings board). The list is alphabetical across directions, so the first row is `Bank Fees #18`. The `placeholder` of the search input is not yet an overlay attribute (decision Q3), so it still says 21.
- It is not archived categories: archived ones are not in the picker (ADR-0136) and are not counted; the 21 vs 24 gap is the four extra live ones and Reconciliation.

**What actually fails (measured).** Three separate causes, in order of weight:

1. **A 2 px layout jump (not about the count).** Opening the picker moves focus from the hero amount to the search field. The amount's underline falls back from its focused width (`--border-width-focus-strong`) to the normal one, the hero is 72 px instead of 74 px and the whole dialog body sits 2 px higher than in the handoff, whose static page still shows the amount focused. Alone this is the whole failure of `--no-match` (probe: underline kept at its focused width gives 0.007 % / 25 px) and most of `category-picker`.
2. The list: first row `Bank Fees #18` vs `Big Purchases` and the list's scroll extent (the visible window is the first six rows).
3. The placeholder text (21 vs 24), visible only on `category-picker` (the other page has a typed query).

Refocusing the amount from the recipe is not an option: the picker closes (21 % / 312,689 px).

**Options and patches** (`docs/plans/ui-redesign/operator-options/`):

| Id | Option | Patch | Cost |
|---|---|---|---|
| D1-a | `placeholder` becomes an overlay attribute and one row rewrites the input's count to 24 (operator decision Q3, not yet built) | `D1-a-placeholder.patch` (`overlay.py`, one toml row) | none; ADR-0147 §4 amendment names it |
| D1-b | The amount keeps its focused underline while the picker is open: `.rd-dialog:has(.rd-catpick:not([hidden])) .rd-dialog__amount { border-bottom-width: var(--border-width-focus-strong) }`. It also removes a real 2 px jump of the dialog when the picker opens | `D1-b-underline-css.patch` (`dialog.css` + regenerated `app.bundle.css`) | edits the vendored `dialog.css` (Q8 says byte-identical: **this violates Q8**, say so in the ADR-0107 §2 amendment) or ships the rule in a new app stylesheet |
| D1-c | The picker list equals the handoff's visible rows. Either (i) a seed modifier `picker-handoff-list` archives the four extra categories for these two pages only (needs a small seed-engine "archive after seeding"; their planned items and rules stay valid, ADR-0089) and the count rows for these pages read 20, or (ii) an overlay op that inserts and removes list rows (ADR-0147 §4 amendment, bigger). **Not built as a patch**: only its pixel effect was measured (first row removed, next row highlighted) | none (proxy) | seed-engine or overlay-engine work |
| D1-d | Accept: a tolerance exception row. Not possible: the ratio is 2.65 % to 3.6 % and an exception needs a reason that is not a data mismatch | - | - |

**Measured** (`ok` passes; `CHAN` = pixels pass at 0.025 % but the app PNG is RGBA and the reference RGB, so `handoff.compare` reports a size mismatch; see "Harness findings"):

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| category-picker | baseline | FAIL 3.333%/19457 | FAIL 2.753%/-1 | FAIL 3.614%/2731 |
| category-picker | D1-a (placeholder) | FAIL 3.332%/19457 | FAIL 2.752%/-1 | FAIL 3.606%/2731 |
| category-picker | D1-a + D1-b (real CSS rule) | FAIL 0.855%/2731 | FAIL 1.043%/-1 | FAIL 2.302%/2731 |
| category-picker | D1-a + D1-b + D1-c (list proxy) | ok 0.000%/0 | CHAN 0.025% | ok 0.000%/0 |
| category-picker--no-match | baseline | FAIL 2.653%/16978 | FAIL 2.811%/6570 | FAIL 1.327%/2299 |
| category-picker--no-match | D1-a (placeholder) | FAIL 2.653%/16978 | FAIL 2.811%/6570 | FAIL 1.327%/2299 |
| category-picker--no-match | D1-a + D1-b (real CSS rule) | ok 0.007%/25 | ok 0.010%/25 | ok 0.024%/25 |

**Recommendation (mine).** D1-a + D1-b + D1-c(i). D1-a and D1-b make `--no-match` green and cut `category-picker` to the list rows; D1-c(i) finishes it. With the archive modifier N is 20 on these two pages (the handoff's 21 minus Reconciliation, exactly ADR-0151's rule), so these two pages exclude the global 21 to 24 row and carry their own 21 to 20 rows (button and placeholder).

## D2. Q4: budget-row bar labels (page `plan/budget`)

**Status: passes at all three shards today (0.000 % / 0 px)**; nothing is blocked.

- Handoff `plan/budget.html` has seven `role="img"` bars whose `aria-label`s do not add to 100: `39/60`, `0/100`, `45/60`, `71/30`, `5/90`, `90/10`, `3/100` (value-inventory §5 row 8: "left" is the empty-cell count times ten, and the spent share rounds half up).
- App: `view_models.bar_aria_label`: spent floored, left = 100 - spent: `38/62`, `0/100`, `44/56`, `71/29`, `5/95`, `89/11`, `2/98`. ADR-0147 §3: the handoff side is corrected, never the app.
- Existing overlay rows: only the global Today bar row (`78/15` to `77/23`, `optional`, does not match this page). **No row exists for the budget-row bars.** The labels are not painted, so no pixel comparison sees them; they matter only for a DOM or accessibility comparison.

| Id | Option | Patch |
|---|---|---|
| D2-a | Do nothing: no check reads the labels. | - |
| D2-b | Six overlay rows (`aria-label` is an allowed attribute), one per label that differs. Overlay builds and the page stays green. | `D2-b-bar-label-rows.patch` |

**Measured** (the six rows alone on the base tree; `aria-label` is not painted, so the pixels cannot move, the point is that the overlay builds and the page stays green; the overlay also builds for all 106 pages with the patch applied):

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| plan_budget | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| plan_budget | D2-b (6 rows, patch alone) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

**Recommendation (mine).** D2-b: six rows, no code, and the operator's "handoff side is corrected" is then true in the file instead of only in the app. Not urgent.

## D3. Q5: `accounts--empty` shows a net worth over an empty list

**What differs.** The handoff board shows `net worth · 10 accounts`, `34,439.69 PLN`, `assets 36,895.43 · liabilities −2,455.74 · planned −312.54` (phone: `10 ACCOUNTS`) above `No accounts yet.` The app computes the hero from the data: `net worth · 0 accounts`, `0.00`, `assets 0.00 · liabilities 0.00 · planned 0.00`. A net worth of 34,439.69 over no accounts is not a state the app can show without inventing data, so "follow the handoff" has no app-side reading.

**Blocks** `accounts--empty` at all three shards (1.97 % / 11,703 px; 3.25 %; 21.5 % / 26,933 px).

| Id | Option | Patch |
|---|---|---|
| D3-a | Overlay rows rewrite the hero (label, figure and its digit and mark counts, both notes) and the phone caption to the empty values; the global `planned +395.91` row excludes this page. | `D3-a-overlay-rows.patch` (8 toml rows) |
| D3-b | App shows a net worth hero with no accounts. Impossible without fixture data in the app. | - |
| D3-c | Leave red. | - |

**Measured** (the D3-a patch alone on the base tree; the `exclude` on the global planned row keeps this page's hero out of the `planned +395.91` rewrite):

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| accounts--empty | baseline | FAIL 1.973%/11703 | FAIL 3.251%/11703 | FAIL 21.538%/26933 |
| accounts--empty | D3-a (patch alone) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

**Recommendation (mine).** D3-a.

## D4. Afford-it states (pages `today--afford-invalid`, `today--afford-over`, `today`, `today--empty` and every overlay on the Today backdrop)

**Status: all pass at all three shards today** (0.000 % / 0 px; also `today--empty`). The earlier 0.0491 % and 0.0048 % failures are gone after N1.

**What differs, and what makes it pass.** The handoff Today has left `1,399.93` (per day `199.99`), committed `34.60`, afford `164.28`, afford-over `−14.20 · 114.20 over`. The seed has the overdue `Annual insurance` (412.00, 28 Oct, category Other, budgeted) which ADR-0105 counts as committed, so the app has left `987.93` (per day `141.13`), committed `446.60`, afford `105.42`, afford-over `−116.01 · 812.07 over` (1,800.00 less 987.93). ADR-0151 §1 (designer-confirmed) gives `−57.15 per day · 400.07 over`, which is 1,800.00 less the handoff's own 1,399.93 over 7 days; the seed cannot produce it while ADR-0105 holds. Today the page passes through **13 seed-value overlay rows**: left per day, committed (two rows), left (three rows incl. the plan figure and the budget note), `164.28 to 105.42`, the afford-over row (`−116.01 · 812.07 over`, **not** the ADR-0151 figure), the hero note and `34.60 committed · 6 over`, and the three `today--empty` / `today--afford-invalid` rows.

| Id | Option | Patch |
|---|---|---|
| D4-a | Keep (current). The ADR-0151 figure stays the designer's answer for the handoff's own data and is replaced by the seed figure in the overlay. | - |
| D4-b | Overlay the afford-over row to the ADR-0151 text `−57.15 · 400.07 over`. The app produces `−116.01 · 812.07`, so the page would fail: not viable. | - |
| D4-c | Amend ADR-0105: committed counts from today, not the overdue ones (`budget._month_totals`: `start=None` becomes `start=ctx.today`). The app then gives the handoff's 1,399.93, 199.99, 34.60, 164.28 and ADR-0151's `−57.15 · 400.07`: 6 overlay rows go (`199.99`, `34.60`, `1,399.93` twice, `164.28`, `left 1,399.93`), the afford-over row takes the ADR-0151 text, the two budget note rows keep only the `6 to 8 categories over` change (the spent figures alone put 8 categories over), and three page-specific rows change their `old` value to the handoff's. | `D4-c-committed-from-today.patch` |

**Measured:**

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| today | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--afford-invalid | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--afford-invalid | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--afford-over | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--afford-over | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--empty | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--empty | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--loading | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| today--loading | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| plan_budget | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| plan_budget | D4-c | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| plan_forecast | baseline | ok 0.000%/0 | ok 0.001%/9 | ok 0.000%/0 |
| plan_forecast | D4-c | FAIL 0.018%/125 | FAIL 0.028%/132 | ok 0.000%/0 |

**Recommendation (mine).** D4-a. D4-c is a product decision (an overdue, unpaid bill stops lowering "left to spend per day"), reverses ADR-0105 and moves the budget, forecast and ledger figures too; it is not the smallest change. If the operator wants the app to agree with the designer's numbers, D4-c is the way; the table shows what it clears. It also moves `plan/forecast` (its current-period Expenses count overdue items, ADR-0105 amendment 2026-11-21): the committed geometry rows (`uv run python -m tests.visual.test_overlay_geometry`) would be regenerated, and the tests that pin ADR-0105's overdue rule (budget, today, forecast) change.

## D5. Should typed values survive a new-entry tab switch (pages `new-entry--happened`, `--planned`, `--repeats-fixed`, `--repeats-formula`)

**What the app does today (probe, scratch DB).** The three tabs are links `hx-get="/add?when=<tab>&dialog=1"` that swap a fresh dialog into `#modal-root`; the request carries none of the form's values. After typing `35.50`, Takeaway, Credit Card and a note on `happened` and clicking `planned`, the amount is empty, no category is checked and the note is empty (the account select keeps Credit Card only because it is the most recently used account). `repeats` and back to `happened`: the same. The handoff pages show 35.50 / Takeaway / Credit Card / note on each tab because they are static mocks.

**Blocks: nothing.** The harness opens each page's own route and types (`handoff_newentry.DIALOG_RECIPES`), it never switches tabs, so no comparison depends on the answer.

| Id | Option | Patch |
|---|---|---|
| D5-a | Keep: a tab switch starts a fresh form. | - |
| D5-b | Carry the typed values: the tab links add `hx-include="closest form"` and `hx-params="not _csrf_token"`, and `form_responses.open_new_entry` passes the query values as `posted` (the same path the hero refresh already uses). No new route, no client script. | `D5-b-carry-typed-values.patch` |

**Measured:** new-entry pages unchanged by D5-b (the harness never clicks a tab); the probe with the patch applied is below.

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| new-entry--happened | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--happened | D5-b | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--planned | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--planned | D5-b | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-entry--repeats-fixed | baseline | ok 0.000%/0 | FAIL 7.343%/37290 | FAIL 3.164%/1511 |
| new-entry--repeats-fixed | D5-b | ok 0.000%/0 | FAIL 7.343%/37290 | FAIL 3.164%/1511 |
| new-entry--repeats-formula | baseline | FAIL 0.164%/1878 | FAIL 0.107%/1116 | FAIL 0.065%/504 |
| new-entry--repeats-formula | D5-b | FAIL 0.164%/1878 | FAIL 0.107%/1116 | FAIL 0.065%/504 |

D5-b probe (type on `happened`, then click `planned`, `repeats`, `happened`):

| step | baseline (`d4c06a8`): amount / category / account / note | with D5-b: amount / category / account / note |
|---|---|---|
| typed on `happened` | 35.50 / Takeaway / Credit Card / lunch | 35.50 / Takeaway / Credit Card / lunch |
| click `planned` | empty / none / Credit Card / empty | 35.50 / Takeaway / Credit Card / lunch |
| click `repeats` | empty / none / Credit Card / empty | 35.50 / Takeaway / Credit Card / lunch |
| back to `happened` | empty / none / Credit Card / empty | 35.50 / Takeaway / Credit Card / lunch |

(The repeats tab names its fields `default_amount` and `default_description`; the patch renames them on the way in and out.)

**Recommendation (mine).** D5-b: it is the behaviour the handoff boards imply, it is small and it has no visual effect. Fields that exist only on one tab (due date, cadence) are not carried; the amount, category, account and note are.

## D6. ADR-0089 "after planned" counts overdue items (pages `accounts` family)

**What differs.** The handoff accounts board counts only the planned items dated after today inside the period: hero `planned −312.54` (Credit Card 1 Nov −277.94 and −11.31, Checking 5 Nov −23.29), Checking `→ 3,662.52 after planned`, no note on Checking EUR. ADR-0089 counts every unpaid planned item of the fiscal period, **overdue and due-today included**: the app shows `planned +395.91` (adds Annual insurance −412.00 and the Tax refund +1,120.45 due 31 Oct), Checking `→ 3,250.52`, Checking EUR `→ −5,480.70`. Two overlay rows now rewrite the handoff to the app's numbers; the Checking EUR note has no element in the handoff (a 10 px height difference at 1024).

**Blocks** (baseline): `accounts` (0.088 % / 132 px at 1440L, SIZE at 1024D), `delete-account--blocked`, `--blocked-planned`, `new-account`, `new-account--error`, `--filled`, `edit-account`, `row-menu--account` (the same 132 px / 10 px), plus the four pages of D8 that carry the same backdrop (they stay red for their own reasons). 8 pages x 2 shards (1440L, 1024D); 375L already passes.

| Id | Option | Patch |
|---|---|---|
| D6-A | `account_planned.planned_net_by_account` takes `after` (today): the first counted day is `max(period_start, today + 1)`; `compute_accounts_planned` passes today. The two overlay rows are deleted. | `D6-A-after-today.patch` |
| D6-B | Keep ADR-0089 as is; the two overlay rows stay (the Checking EUR note stays a pixel difference). | - |

Amendment text for ADR-0089 if D6-A is chosen:

> **Amendment 2026-11-26 (T-UR00b, operator decision): only items after today.** Decision 2 changes: the net counts unpromoted planned rows and recurring occurrences dated **after today** and before the period end (`today < date < period_end`). Overdue items and items due today are no longer in the per-account net, the projected balance or the hero's planned figure. Reason: the handoff Accounts board (follow the handoff, operator decisions 2026-11-25). Overdue unpaid items still lower "left" on Today and Budget (ADR-0105); they no longer lower the projected end-of-period balance of an account. `planned_net_by_account(..., after=today)`; the window start (`period_start`) is only the lower bound before today.

Tests that pin the old rule and need the new expectation (not run here; the wave tester finds the rest): `tests/unit/services/test_account_planned.py` (`test_overdue_unpromoted_planned_counted`, `test_recurring_overdue_unpromoted_counted`), `tests/unit/services/test_planned_deleted_account.py`, `tests/integration/web/test_accounts_planned.py`, `tests/integration/invariants/test_inv_07_period_window.py`.

**Measured** (D6-A applied with the two rows deleted; the second variant is the final patch alone on a clean base, `accounts` page only):

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| accounts | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| accounts | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| accounts | D6-A (patch alone) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| delete-account--blocked | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| delete-account--blocked | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| delete-account--blocked-planned | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| delete-account--blocked-planned | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-account--error | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account--error | D6-A | ok 0.000%/0 | FAIL 2.568%/4266 | ok 0.000%/0 |
| new-account--filled | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account--filled | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| edit-account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| edit-account | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| row-menu--account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| row-menu--account | D6-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

`new-account--error` at 1024D shows 2.57 % / 4,266 px once the height difference is gone: a focus ring on the name field after the 422 that the handoff does not show (1440L and 375L pass). That is a separate item (the app focuses the first invalid field after a failed save, a deliberate a11y behaviour, `derived.md`), not part of D6.

**Recommendation (mine).** D6-A under the "follow the handoff" rule. Cost to say out loud: an overdue unpaid bill stops showing in an account's "after planned" figure. Choose D6-B if the projection should stay conservative.

## D7. `force-password` and `--error` (`/settings/password`)

**What differs.** Handoff: `signed in as parent@example.test`, title, lede `Your password was reset by an admin. Choose your own to continue.`, two stacked fields (new, confirm; hint `12+ characters`), a block `[ save and continue ]` and a plain `sign out` link. App: the shared password form: a `Your password needs rotating` note, a **current-password field** (the service requires it), new and confirm side by side, and `sign out instead` as a quiet button. Error variant copy: handoff `▲ Passwords don’t match`, app `▲ The two new passwords don't match.` (`MSG_MISMATCH`, shared with Settings · security, contract-pinned).

**Blocks** `force-password` and `force-password--error` at all three shards (3.7 % / 24,990 px; 6.1 %; 11.6 %).

| Id | Option | Patch |
|---|---|---|
| D7-a | Template only: the forced page becomes its own form (new + confirm, handoff markup, no current-password field) posting to `/settings/password`. **The service still rejects the post** (current password required): the page is for measurement only until D7-b. Plus one overlay row for the email (`parent@` to the seed owner) and one for the 422 copy. | `D7-a-template-and-rows.patch` |
| D7-b | Service: a forced rotation skips the current-password check. Not applied, not measured; the change is listed below. | (text below) |

D7-b, the change a forced rotation needs (a security decision, listed not applied):

- `services/password_change.change_own_password(..., forced: bool = False)`: when `forced` is true the user must have `must_change_password` (read from the DB row, never from the form): skip the `current_password` presence and `hasher.verify` steps and the `bad_current_password` audit. The caller passes `forced=user.must_change_password`; a normal change keeps the current-password check.
- The new password must differ from the temporary one: with `forced`, add `hasher.verify(new_password, user.password_hash)` and return `MSG_SAME_AS_CURRENT` on `new_password` (today `validate_new_password` compares the typed current password, which a forced form does not have).
- `PasswordChangeRequest.current_password` becomes optional for a forced call; `validate_new_password` skips the same-as-current branch when empty (already does).
- The throttle (ADR-0072/0075) and the session rotation, other-session revocation and audit row are unchanged; the commit still compares the stored hash (`_commit_change`, stale guard).
- Route `settings_password.py`: read the user's flag, pass it, and render the forced template without the `current_password` field.
- ADR note (ADR-0074 amendment):

> **Amendment 2026-11-26 (T-UR00b, operator decision): forced rotation needs no current password.** A user with `must_change_password` has just signed in with the one-time password an admin handed over, so asking for it again protects nothing. The form takes the new password and its confirmation. The server decides forced-ness from the stored flag, never from the request. The new password must differ from the temporary one. Every other rule of ADR-0074 (length, bcrypt limit, throttle, session rotation, audit) is unchanged.

**Measured** (template + the two rows; the service change is not applied):

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| auth_force-password | baseline | FAIL 3.709%/24990 | FAIL 6.061%/24760 | FAIL 11.618%/14716 |
| auth_force-password | template + email row | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| auth_force-password--error | baseline | FAIL 3.339%/17224 | FAIL 5.457%/17121 | FAIL 12.529%/14716 |
| auth_force-password--error | template + email row | FAIL 0.120%/217 | FAIL 0.197%/217 | FAIL 0.509%/217 |
| auth_force-password--error | template + email + copy rows | ok 0.023%/14 | ok 0.038%/14 | ok 0.098%/14 |

The email row is a harness fact (the board signs in `parent@example.test`, the harness signs in the seed owner); with it `force-password` is green. The copy row turns the 422 text of the handoff into the app's.

**Recommendation (mine).** D7-a + D7-b if the operator accepts the security reading above; otherwise keep the current-password field and accept both pages red (the field is a layout difference of 24,990 px, too big for an exception).

## D8. Accounts dialogs

**What differs and blocks.** (After D6-A the backdrop of all of these is clean, so the numbers below are the dialogs themselves.)

| Item | Handoff | App | Pages |
|---|---|---|---|
| liability and its credit limit | `edit-account--liability`: Investments A flagged liability, no credit-limit field | a liability needs a positive credit limit (`web/params.credit_limit_amount`, "positive credit limit required"); the field shows when `counts as` is liability | `edit-account--liability` (12.4 % / 109,118 px at 1440L) |
| new-account `as of` | `as of` date field | shown, `min = max = today`; no stored opening date | none: `new-account*` pass (the frozen day equals the handoff's date); a stored date needs a migration and is a product call, not a pixel one |
| reconcile extras | `reconcile`, `--liability`: balance field, snapshots newest first, no other control | adds `record as` (category), `also save a balance snapshot` and `preview`; the hero is a static difference | `reconcile` (13 %), `reconcile--liability` (12.4 %) at all shards |
| delete-account | names `Investments E`, an 11th account its list of 10 does not show | the seed adds E (`unreferenced-account` modifier), the backdrop has 11 rows (68 px more at 1440) | `delete-account` (size mismatch at all shards) |

| Id | Option | Patch |
|---|---|---|
| D8-L | The credit limit is optional (blank = no limit, which `domain.accounts.credit_limit_error` already allows) and only asked of a credit card (`data-show-when="is_liability=on type=credit card"`); a typed limit must still be positive. | `D8-L-credit-limit-optional.patch` |
| D8-L2 | Keep the field: the page stays red (+45 px of dialog). | - |
| D8-R | Template: remove `record as`, the snapshot checkbox and `preview` from the reconcile dialog. Measured effect below. It is **not enough**: the hero must update live as the user types (today `preview` re-renders it; the handoff shows `+4.29` for `3,690.10`), the snapshot rows must be the handoff's (seed), and the liability dialog's `Limit ... implied used ...` help line differs. The service side (`record as` default = Reconciliation category, snapshot always or never) is a product decision. | `D8-R-reconcile-extras-out.patch` (template only) |
| D8-E | `delete-account`: an overlay op that inserts the 11th row into the handoff backdrop (ADR-0147 §4 amendment: the overlay is text and attributes only today). Not built; the proxy (the app's `Investments E` row removed, hero count `10`) shows what a perfect insertion buys. | none (proxy) |
| D8-T | `as of`: a migration and an ADR. No pixel effect. | - |

**Measured:**

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| edit-account--liability | baseline | FAIL 12.480%/109118 | SIZE 21.32% | FAIL 22.473%/77367 |
| edit-account--liability | D6-A only | FAIL 12.392%/109118 | FAIL 18.187%/122131 | FAIL 22.473%/77367 |
| edit-account--liability | D8-L / D8-R (D6-A applied) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| reconcile | baseline | FAIL 13.009%/94119 | SIZE 22.51% | FAIL 26.510%/59334 |
| reconcile | D6-A only | FAIL 12.921%/94119 | FAIL 19.396%/98921 | FAIL 26.510%/59334 |
| reconcile | D8-L / D8-R (D6-A applied) | FAIL 0.335%/4665 | FAIL 0.463%/4665 | FAIL 1.271%/4665 |
| reconcile--liability | baseline | FAIL 12.356%/89512 | SIZE 21.27% | FAIL 23.246%/40769 |
| reconcile--liability | D6-A only | FAIL 12.268%/89512 | FAIL 18.141%/92083 | FAIL 23.246%/40769 |
| reconcile--liability | D8-L / D8-R (D6-A applied) | FAIL 7.361%/55881 | FAIL 9.249%/32270 | FAIL 14.778%/32613 |
| delete-account | baseline | SIZE 10.47% | SIZE 11.65% | SIZE 12.89% |
| delete-account | D6-A only | SIZE 10.42% | SIZE 10.93% | SIZE 12.89% |
| delete-account | D8-E proxy | ok 0.000%/0 | ok 0.000%/0 | ok 0.011%/50 |
| new-account | baseline | FAIL 0.088%/132 | SIZE 3.28% | ok 0.000%/0 |
| new-account | D6-A only | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-account | D8-L / D8-R (D6-A applied) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

D8-R, after the template change: `reconcile` 0.335 % / 4,665 px at 1440L (the typed `3,690.10` and `+4.29` hero, and the snapshot rows `01 APR 3,702.44` / `01 MAR 3,415.02` vs the seed's), `reconcile--liability` 7.4 % / 55,881 px (typed `12,400.00`, hero `−121.63`, the help line, two snapshots vs one).

**Recommendation (mine).** D8-L (cheap, clean rule: a credit limit belongs to credit cards). D8-E for `delete-account` (proxy green at three shards). For the reconcile pair, take D8-R's template removal only together with a live hero and a snapshot decision; until then keep both red (they are the largest remaining pages, 12 to 26 %). `as of` stays out of this wave.

## D9. `today--flash`: 8 px between two flash regions

**What differs.** The handoff has one `#flash-region` holding the saved flash and the error flash, 8 px apart (`gap: var(--space-2)`). The app has two live regions, `#flash-region` (polite) and `#flash-region-assertive` (alert), each with `margin-bottom: var(--space-4)`; the page is 8 px taller at every width (1440: 1,591 vs 1,583; 1024: 1,623 vs 1,615). **Blocks** `today--flash` at all three shards (size mismatch).

| Id | Option | Patch |
|---|---|---|
| D9-A | Merge into one `#flash-region` (role status, polite). The error flash already carries `role="alert"`, so it is still announced assertively. Changes: `layouts/base.html` (drop the assertive div); `web/errors.py` (`region = "flash-region"`); `web/users_admin.py` (`FLASH_REGION`); `fragments/flash/error.html` (role/aria-live of the OOB wrapper); `rd/js/app-toast.js` (OOB regex, `show()` appends and replaces only a flash of its own kind so the saved and the error flash sit side by side, the in-dialog region roles, the offline fallback); the harness selector in `tests/visual/handoff_states.py`. | `D9-A-merge-flash-region.patch` |
| D9-B | Change the vendored CSS (`.rd-flash-region` margin). Not possible without breaking every page with one region (margin 16 px) and **violates Q8** (vendored CSS byte-identical). | - |

Tests that name `flash-region-assertive` and would change with D9-A: `tests/contract/test_shell.py`, `tests/integration/web/test_missing_form_fields.py`, `tests/integration/web/test_accessibility.py`, `tests/integration/web/test_errors.py`, `tests/ui_map/settings.py`, `tests/ui_map/shell.py`, `tests/e2e/test_rd_today_skeleton.py`, `tests/e2e/test_rd_toast.py`, `tests/e2e/test_htmx_error_flash.py`.

**Measured:**

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| today--flash | baseline | SIZE 8.76% | SIZE 10.86% | SIZE 13.75% |
| today--flash | D9-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

**Recommendation (mine).** D9-A. The accessibility cost is real but small (the alert role stays on the flash); the contract and e2e edits are mechanical (the selector id). The decision is yours because it changes what two regions mean for screen readers.

## D10. `one-time-password`: the generated password

**What differs.** The handoff shows `kT4p-9wrx-Lomb` (12 characters in three groups of four). The app shows `secrets.token_urlsafe(16)`: 22 random characters (ADR-0061 §8, about 128 bits), different every run. **Blocks** `one-time-password` at all three shards (0.145 % / 117 px, 0.241 % / 119 px, 0.591 % / 212 px: the secret's text).

| Id | Option | Patch |
|---|---|---|
| D10-A | The visual server (`tests/visual/frozen_server.py`) overrides the web dependency `get_token_source` with a token port that returns the board's sample for the 16-byte request (the generated password) and the CSPRNG for everything else. Test-only; production is untouched. | `D10-A-token-port.patch` |
| D10-B | Change the generator to a 4-4-4 format of 12 characters (about 71 bits). Weakens ADR-0061 §8; needs an ADR amendment; pointless once D10-A exists. | - |

**Measured:**

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| one-time-password | baseline | FAIL 0.145%/117 | FAIL 0.241%/119 | FAIL 0.591%/212 |
| one-time-password | D10-A | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

**Recommendation (mine).** D10-A.

## D11. Category swatch: `Takeaway` is `orange` on the board and `tangerine` in the dialog (page `edit-category`)

**What differs.** Same category, two colours in the handoff: the board and every list paint Takeaway with the preset `orange` (`#ff9f43`); `edit-category` shows the dialog's own ten swatches with `tangerine` (`#f97316`) selected (ring) and a preview chip in tangerine. The dialog palette is not the board palette. The app stores `#ff9f43`, which is none of the ten swatches, so it selects none and previews orange. Decision Q19 (palette names and hex) gave the handoff's names to the app; this pair is the part it did not settle. **Blocks** `edit-category` at all three shards (0.085 % / 1,847 px; 0.118 % / 1,839 px; 0.261 % / 1,909 px: the preview chip and the missing ring).

| Id | Option | Patch |
|---|---|---|
| D11-S | The edit dialog selects the swatch nearest to the stored hue (RGB distance) and previews that swatch: `settings_view.category_form_view` (about 12 lines). Takeaway is shown as tangerine in the dialog and stays orange on the boards, exactly as the handoff. A save without touching the colour would store the swatch's colour (a silent recolour: say so in the ADR). | `D11-S-snap-to-nearest-swatch.patch` |
| D11-O | Overlay: `data-color` becomes an overlay attribute and one row turns the preview chip to `orange`. The ring on the selected swatch cannot be added (no `checked`), so the page stays red. | `D11-O-overlay-chip.patch` |
| D11-X | Recolour Takeaway to tangerine in the seed. Every board and list that shows Takeaway then differs (its chip is orange there). | - |
| D11-T | Tolerance exception for `edit-category` (cluster 1,909 px, ratio up to 0.26 %). | - |

**Measured:**

| page | variant | 1440L | 1024D | 375L |
|---|---|---|---|---|
| edit-category | baseline | FAIL 0.085%/1847 | FAIL 0.118%/1839 | FAIL 0.261%/1909 |
| edit-category | D11-O (overlay chip) | FAIL 0.017%/447 | FAIL 0.023%/433 | FAIL 0.050%/447 |
| edit-category | D11-S (snap) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-category | baseline | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |
| new-category | D11-S (snap) | ok 0.000%/0 | ok 0.000%/0 | ok 0.000%/0 |

**Recommendation (mine).** D11-S. It is the only option that reproduces the handoff dialog, and `derived.md` already lists "snap to the nearest preset" as the open designer question.

## Harness findings (not decisions, listed so they are not lost)

- **Channel mismatch.** `category-picker` at 1024D: the app's screenshot is RGBA, the reference RGB, same pixel size. `handoff.compare` treats a differing channel count as a size mismatch and fails the page whatever the pixels (0.025 % in the table). A one-line normalisation in `handoff._decode` or `compare` (compare RGB when sizes are equal) fixes it. Seen on this one page of 36 measured.
- `new-entry--repeats-fixed` fails at 1024D and 375L (7.34 % / 37,290 px, 3.16 % / 1,511 px) although it passes at 1440L, and `new-entry--repeats-formula` fails everywhere by a small cluster (0.164 % / 1,878 px at 1440L). Neither is part of D1 to D11.
- `new-account--error` at 1024D (see D6).

## Method, repeatable

Each option: edit on the scratch worktree, `LABOUT=<dir> VP=<1440|1024|375> TH=<light|dark> python lab.py <overlay stem|pages/...html>` per shard (the lab re-implements `test_reference.py` flow: overlaid handoff via `handoff.serve_handoff`, app on `handoff_seed.build_seed` with `serve_db`, same recipes and `handoff.compare`), then `git diff` to the patch and revert. The patches were generated from the base file text, not from the scratch tree, and checked with `git apply --check` on `d4c06a8`. Combining patches that touch the same file (`handoff_overlay.toml`, `overlay.py`) needs `git apply --3way` or a manual merge; D3-a and D6-A both touch the global `planned` row (D6-A deletes it, D3-a adds `exclude` to it): apply D6-A first and drop the `exclude` line of D3-a.

## Patch index (`docs/plans/ui-redesign/operator-options/`)

All patches are `git apply --check`-clean on `d4c06a8`, one per option, independent of each other except where noted. None is applied on this branch.

| Patch | Touches |
|---|---|
| `D1-a-placeholder.patch` | `tests/visual/overlay.py`, `handoff_overlay.toml` |
| `D1-b-underline-css.patch` | `rd/css/components/dialog.css` (vendored: Q8), regenerated `rd/css/app.bundle.css` |
| `D2-b-bar-label-rows.patch` | `handoff_overlay.toml` |
| `D3-a-overlay-rows.patch` | `handoff_overlay.toml` (also adds `exclude` to the global planned row; skip that line if D6-A is applied first) |
| `D4-c-committed-from-today.patch` | `services/budget.py`, `handoff_overlay.toml` |
| `D5-b-carry-typed-values.patch` | `pages/entries/new-entry.html`, `web/form_responses.py` |
| `D6-A-after-today.patch` | `services/account_planned.py`, `handoff_overlay.toml` (two rows deleted) |
| `D7-a-template-and-rows.patch` | `pages/auth/force-password.html`, `handoff_overlay.toml` (email and copy rows) |
| `D8-L-credit-limit-optional.patch` | `web/account_forms.py`, `pages/accounts/dialog-account.html` |
| `D8-R-reconcile-extras-out.patch` | `pages/accounts/dialog-reconcile.html` (template only) |
| `D9-A-merge-flash-region.patch` | `layouts/base.html`, `web/errors.py`, `web/users_admin.py`, `fragments/flash/error.html`, `rd/js/app-toast.js`, `tests/visual/handoff_states.py` |
| `D10-A-token-port.patch` | `tests/visual/frozen_server.py` |
| `D11-S-snap-to-nearest-swatch.patch` | `web/settings_view.py` |
| `D11-O-overlay-chip.patch` | `tests/visual/overlay.py`, `handoff_overlay.toml` |

Not patched (no diff worth reviewing): D1-c (needs a seed-engine or overlay-engine feature), D7-b (service text above), D8-E (overlay op), D8-T (migration).

Every chosen option still owes its own tests, ADR amendment text and the removal of the overlay rows it makes obsolete; the patches carry the code and overlay side only. The overlay guard (`test_handoff_overlay.py`) and the pinned value tests (`test_overlay_values.py`) were not run here.
