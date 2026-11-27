# Frontend audit: no auto-zoom on field focus (ZOOM: T-UR81, R21)

Date: 2026-11-27. Branch wi/ui/sourdough/ZOOM at 260a2c19 (change: `src/budget_planner/web/static/rd/app/overrides.css` and an e2e test).
Tool: `frontend-visual-audit` skill (Playwright/Chromium). 375x812 light and dark with touch emulation (`has_touch`, `is_mobile`, so `pointer: coarse` is also true), 1024x768 and 1440x900 light.
Data: scratch DB (migrated, login user, 3 accounts, 6 categories, budget defaults for 3 categories, a transaction, a planned entry, a recurring rule); never `data/budget.sqlite`.
Baseline: same DB and browser, `overrides.css` replaced by the merge-base (16010c5a) version through request interception.
Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out/*.png` (`cur_*` = this change, `base_*` = before), 47 scenarios x 4 viewport/theme combinations (cur) and x 2 desktop viewports (base). Raw numbers: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out/results.json`.

## Routes and states (47 scenarios)

Pages: /auth/login, /auth/register, /setup, /invite/badtoken, /today, /today?amount=20.00, /today?amount=99999999 (afford over), /ledger, /ledger with filters open and from, to and search filled, /accounts, /plan?tab=budget, /plan?tab=year, /plan?tab=forecast, /plan?tab=analytics, /settings?tab=categories, fx, prefs, /settings/security, /settings/password, /settings/users (+ /new, /invites/new), /auth/sessions, /auth/reauth.
Dialogs (htmx into #modal-root): new entry happened, planned, repeats, repeats with formula, formula with the multi-select open and its filter typed; category picker open and typed with no match (new entry and edit transaction); budget override; account new, edit, reconcile; category new, edit; edit recurring; edit transaction; edit planned; promote planned; recurring override.
Other: command palette (open, typed with no match), period picker popover (no text field inside), plan year cell editor (click on a cell, "1234.56" typed, scope chip row).

## Diagnostics (all 47 scenarios per viewport; same elements as the baseline)

| Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| 1440 | 0 | see below | 0 | 0 on this change (list below) | 0 |
| 1024 | 0 | see below | 0 | 0 (same list) | 0 (one aborted htmx request, baseline too) |
| 375 light | 0 | see below | 0 | 0 (same list) | 0 |
| 375 dark | 0 | see below | 0 | 0 (same list) | 0 |

overflowingElements (non-zero, none causes page scroll, all pre-existing and equal on the baseline): `pre.rd-hero__loaf` and `rd-auth__loaf` (decorative), `a.rd-tabs__tab` (tab strip scrolls inside its container), forecast SVG `line/svg/text` at 375, the year grid table at 375 and 1024 (scrolls inside its own wrapper, wrapper 311px of 1150px at 375).
Console and request entries, all identical in the baseline run (not CSS related): 404 on /settings/users, /settings/users/new and /settings/users/invites/new (the scratch login user is not an admin; the user dialogs were therefore not audited, they use the same `.rd-input__control` and `select` classes the rule covers); the 422 `/recurring/formula/preview` console line that lands late in the palette scenarios (belongs to the preceding formula dialog: an empty formula is answered 422 and shown inline); an aborted htmx request (`htmx:sendAbort`, ledger filters at 1024, flaky in both runs).

## Font size (the point of the item)

Measured per scenario: computed `font-size` of every visible text-like input, select, textarea and contenteditable (hidden, checkbox, radio, button, file, range excluded), and the product of ancestor `transform: matrix` scale and `zoom`.

- 375 light and dark, in the app shell (every route and dialog above except the auth pages): 0 fields below 16px; minimum 16px in all of them (field counts: ledger filters 6, new entry 5 / 5 / 7 / 8 with the formula and multi-select filter, category picker 6, palette 2, year cell editor 1, account dialogs 6 / 5 / 2, category 2, recurring edit 7, afford 1). Ancestor scale or zoom below 1: 0 anywhere. Hero amount (`.rd-dialog__amount`, 56px) unchanged.
- The four fields the item names: `.rd-catpick__input` 16px (was 14px), `.rd-year-editor__input` 16px (was 11px), `.rd-msel__filter-input` 16px (was 13px), `.rd-palette__input` 16px.
- **Auth pages at 375: 14px (finding 1).**

## Layout with the bigger text

- Year cell editor (375): input 76x40 in a 78x42 cell, inside the cell box, row height 42 (unchanged cell height), page horizontalScroll false, the grid scrolls in its own wrapper as before; scope chip row wraps to two lines under the edited row. "1234.56" (7 characters) is fully visible but tight (scrollWidth 79 vs clientWidth 76; the glyphs fit, the padding does not): a wider amount such as "12345.00" will scroll inside the field (finding 2, low).
- Category picker (bottom sheet at 375): search field full width with the esc key hint, rows unchanged, no clipping. Multi-select filter: field and clear button on one line, option row below, no overflow. Palette: input full width, no overflow, no-match state fine.
- Afford field at 375 with 8 digits typed: the 64px wide input clips the number (`afford` scrollWidth > clientWidth); same width as before, now with 16px text (finding 3, low).

## Desktop unchanged

1440 and 1024: 94 scenario pairs compared against the baseline. Field counts, minimum font size and small-field counts equal in every pair; diagnostics equal (the only differences are the flaky aborted htmx request in ledger filters). PNGs byte-identical in 90 of 94; the other four are data-driven: /settings/password and /auth/sessions at 1440 and /auth/sessions at 1024 (the cur run has fewer login sessions than the base run, which runs after it, so the sessions list differs), and the period picker at 1024 (a 2x44px region in the popover). The rule is gated on `(width < 48rem), (pointer: coarse)`, so 13/14px controls stay at 1024 and 1440.

## Step 3b

- No template changed (CSS and an e2e test only): no arithmetic, float or literal added; rendered amounts (12.34, 50.00, 300.00 budget cells, 2,500.00) equal the seeded values.
- No duplicate ids in any of the 47 x 4 runs, including after the dialog, picker, palette and year cell swaps. Swap targets (#modal-root) unchanged.
- Failing saves: not re-run, no form, handler or template changed; the 422 formula preview and the year cell editor open and cancel without error.

## Findings

1. **Auth pages keep 14px fields (blocking for R21 "fix all"), layout.** /auth/login, /auth/register, /setup (and /invite/{token}, /auth/reauth, which share it) at 375 touch: `input#email`, `input#password`, reauth `input#current-password` are 14px. `templates/layouts/auth.html` links `app.bundle.css` but not `rd/app/overrides.css` (`layouts/base.html:27` does), so the new rule never reaches them. Fix: link the overrides stylesheet in `layouts/auth.html` (or move the rule into the bundle). Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out/cur__375__auth-login.png`, `cur__375__auth-register.png`, `cur__375__setup.png`, `cur__375__reauth.png`.
2. **Year cell editor is tight at 16px (low).** `cur__375__year-cell-editor.png`: 76px input holds 7 characters with no slack. Suggest less side padding for `.rd-year-editor__input` under 48rem.
3. **Afford input clips a long amount (low).** `cur__375__today-afford-over.png`: 64px input, 8 digits typed.

Verdict (first pass, 260a2c19): FINDINGS (1 blocking: auth pages). See the re-check below for the final verdict.

## Re-check (abbc7e73)

Date: 2026-11-27. Branch wi/ui/sourdough/ZOOM at abbc7e73 (the three fixes plus the merge of ui/sourdough with YEARCHIP's year-cell scope chips). Tool: `frontend-visual-audit` skill (Playwright/Chromium), scratch DBs only (never `data/budget.sqlite`): one dev-mode DB with the login user, an account, two categories with budget defaults and one pending invite (created with `services.invites.create_invite`, known token), and a second DB started with `BUDGET_ENV=test` and `BUDGET_PLANNER_SETUP_TOKEN_HASH` set so `/setup` is open (in dev mode the dev bootstrap admin keeps setup closed). Viewports 1440x900 and 1024x768 light, 375x812 light and dark with touch emulation (`has_touch`, `is_mobile`). The "before" state of the auth pages is the same page with the `overrides.css` request aborted (`-NOOVR` screenshots).
Screenshots and raw numbers: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out2/`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out3/`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out4/` (`results.json` in each; `<vp>__<scheme>__<name>.png`).

### Routes x viewports

| Route | 1440 | 1024 | 375 light | 375 dark |
|---|---|---|---|---|
| /auth/login, /auth/register | audited | audited | audited | audited |
| /auth/reauth | audited | audited | audited | audited |
| /setup (token link) | audited | audited | audited | audited |
| /invite/{token} | audited | audited | audited | audited |
| /today, /today afford with 8 digits | audited | audited | audited | audited |
| /plan?tab=year, year cell editor with "12345.00" | audited | audited | audited | audited |
| /ledger | audited | audited | audited | audited |
| dialogs: new entry, edit transaction, new account | audited | audited | audited | audited |

Dark was run at 375 only; 1440 and 1024 light. /auth/reauth, /setup and the afford typing were rerun (see the note at the end).

### Diagnostics

| Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| 1440 | 0 | 0 (all routes) | 0 | 0 | 0 |
| 1024 | 0 | 0, except the year grid (inside its scroll wrapper, pre-existing, as in the first pass) | 0 | 0 | 0 |
| 375 light | 0 | 1 on /today, dialogs and auth pages (`pre.rd-hero__loaf` / `rd-auth__loaf`, decorative, pre-existing); year grid 11 to 20 (own scroll wrapper, pre-existing) | 0 | 0 | 0 |
| 375 dark | 0 | same as light | 0 | 0 | 0 |

No page scrolls horizontally anywhere. The one console error per `-NOOVR` run is the aborted stylesheet request caused on purpose; none in the real runs.

### Finding 1 (auth pages 14px): fixed

`layouts/auth.html` now links `rd/app/overrides.css`. At 375 touch, light and dark, every field is 16px (computed): /auth/login (email, password), /auth/register (2 fields), /auth/reauth (current-password), /setup (email, name, password, confirm), /invite/{token} (email, name, password, confirm). Without the stylesheet the same fields are 14px, so the link is what changes them. Desktop: the auth fields stay 14px at 1440 and 1024 (the rule is gated on the touch query).
Layout vs before: /auth/login, /auth/register and /auth/reauth full-page screenshots are byte-identical with and without the stylesheet at 375 and at 1440 (the fields are empty, same box heights); /setup and /invite differ only in the glyph size of the placeholder text ("name@example.com", "Your name", the prefilled invite email). Viewed: nothing wraps, shifts or clips; heading, buttons and loaf unchanged. Screenshots `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out3/375__light__setup.png`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out2/375__dark__invite.png`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out2/375__light__auth-login.png`.

### Finding 2 (year cell editor tight at 16px): fixed

375 light and dark, editor typed with "12345.00" (8 characters): font 16px, input 76x38 in its 78x40 cell, scrollWidth 76 = clientWidth 76 (no clipping), inside the cell box; row heights before and after opening identical ([20, 40, 40]); the cell did not move. The YEARCHIP scope chips ("this month only" preselected, "every March") sit directly below the cell; the chip row is fully inside the viewport (March: 117 to 367 of 375; December, last column: 96 to 367, shifted left to stay in view), no overlap with the edited cell, no page scroll. In a short viewport (375x560, cell near the bottom) the chips stay below the cell and in the viewport (cell 400-440, chips 444-484); the flip-above case was not triggered at that size and is YEARCHIP's own behaviour. Desktop: editor unchanged (11px, 83x38 at 1440, 76x38 at 1024, "12345.00" not clipped, chips under the cell). Screenshots `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out2/375__light__year-editor-12345.png`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out2/375__dark__year-editor-last-col.png`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out4/375__light__year-editor-short-viewport.png`.

### Finding 3 (afford input clips 8 digits): fixed, with a note

375: the afford input is 96px wide (was 64px) with 16px text; typing "12345678" shows all 8 digits (scrollWidth 96 = clientWidth 96), screenshot `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/ZOOM/out3/375__light__afford-typed-8.png`. Note (low, not blocking): a longer string still scrolls inside the field ("1234567.89", 10 characters, by 4px; "99999999.99" by 14px), and the server-rendered formatted value "12,345,678.00" from `?amount=12345678` clips too. Desktop unchanged (80px, 14px).

### Spot check at 375 (touch), light and dark

New entry (5 fields), edit transaction (5), new account (6), /today (1), /ledger (1): all fields 16px, none clipped. Desktop 1440 and 1024: the same pages keep their 13/14px fields and year editor 11px (rules gated on the touch query).

### Step 3b

The re-check adds one `<link>` in `layouts/auth.html`: no arithmetic, float or literal. No duplicate ids on any run; swap targets (`#modal-root`) unchanged; dialogs and the year cell editor open and close without error; rendered values equal the seeded ones (300.00 and 2,500.00 budget cells, afford value as typed). Failing saves: not re-run, no form, handler or route changed.

Note on the run: a first attempt failed on `/auth/reauth` (my script awaited htmx with a string eval that the CSP blocks) and on `/setup` (dev mode keeps setup closed); both were rerun with the setup described above and are reported from the rerun.

Final verdict: CLEAN. The three findings are fixed (finding 3 with the noted long-string limit); the five diagnostics are clean; desktop unchanged.
