# Frontend visual audit: T-UR04a shared fragments

Task: T-UR04 fragments bullet (docs/plans/ui-redesign/tasks.md), branch wi/ui/sourdough/UR04a at 295ed81b. ADR-0107, ADR-0150.
Run with the frontend-visual-audit skill method (Playwright, chromium), heavy lock /tmp/ui-redesign-heavy.lock held and released.

## What was audited

No page includes the eight fragments yet, so each was rendered through the app Jinja env
(`build_jinja_env`) with the contexts of tests/ui_map/test_rd_shared_fragments.py into scratch pages that link
/static/rd/css/app.bundle.css and the rd JS (reveal, expand, filters, formula, dialog, row-menu, palette, shortcuts,
combobox, amount-input). Scratch pages and a static server (symlink to the worktree static dir) lived only in the
scratchpad; no repo files other than this record changed, no database used.

Scratch pages (the "routes"), each at 1440, 1024 and 375 (48 rows):
category-picker (closed, open, no-match), formula (2 components, single), formula-component,
amount-input (field, field with error, hero with error), period-picker (month open, year open), period-nav (month, year;
popover opened by click), row-menu (popover opened by click), pagination (page 2, first page).

## Diagnostics (all 48 rows identical)

| Scratch page | 1440 | 1024 | 375 |
|---|---|---|---|
| all 16 pages above | hs=false ov=0 dup=0 console=0 reqfail=0 | same | same |

horizontalScroll=0, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0 (includes HTTP >= 400, so the
sprite and fonts resolve). Each fragment alone has no duplicate ids.

## Behaviour with the rd JS (1440 and 375)

- row-menu: click opens the popover; ArrowDown moves to the next item, Home goes to the first; Escape closes and focus returns to the trigger. End goes to the last item (cancel at 375; at 1440 cancel is not in the tab order for the desktop popover, End stayed on delete; matches handoff row-menu.js, not a finding). At 375 the menu is the bottom action sheet with grabber and cancel (matches the board).
- period-nav: trigger opens the period popover; Escape closes.
- category-picker: search button sets aria-expanded=true and reveals the panel (at 375 the panel is the sheet variant); typing "sal" filters to Salary; ArrowDown then Enter picks via the hidden input name=category (combobox.js contract; recent radios are unchecked, so a radio-checked probe is not the right assertion).
- formula: "add component" adds a component with indexed names components[2][...]; remove returns to 2; multiselect trigger toggles aria-expanded.
- amount-input: select-on-focus works (value selected); non-numeric characters are blocked by beforeinput; blur does not reformat (by design, "the server returns the formatted value").
- Console errors during all interactions: 0.

## Comparison with the handoff boards

Screenshots of boards (docs/design/rising-dough-frontend/pages/overlays/category-picker, category-picker--no-match,
period-picker, period-picker--year, row-menu--transaction, row-menu--upcoming, edit-recurring--formula, plan/budget,
plan/year) were taken at 1440 and 375 and compared with the fragment renders: chip colours, search field, option list,
period popover (year header, cell highlight, note), row-menu sheet, formula row (sign segmented control, percent, "of",
multiselect, remove), pagination (newer / page n / older, recently deleted link) and the hero amount with error line
match in structure, spacing and type. ledger/actual and overlays/new-entry boards could not be captured by the
script (the actual board redirects, new-entry has no such file); pagination was compared by markup against the
test contract instead.

Known gap (as briefed, not a finding): the category option direction label renders "expense" where the board shows
"↓ expense". It needs a direction_label filter; follow-up.

Screenshots (viewed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/out/category-picker-open__1440.png, row-menu__375.png, formula__1440.png, period-nav__1440.png,
amount-hero__375.png, pagination__375.png, and the matching board__*.png in the same directory. Other pages and widths are in
the same directory (<page>__<width>.png) and json in res.json and beh.json.

## Step 3b (template logic and contract)

- rg over the eight templates for `float`, `{% set %}`, `style=`, `/ 100`, `* 100`, literal currency codes, round/int/sum filters and arithmetic inside `{{ }}`: no hits (only a currency literal inside the row-menu header comment).
- Rendered numbers: none computed in the templates; amounts (next_amount, title, value, currency) are passed in already formatted.
- hx-target/hx-swap: only row-menu action items carry them, values come from the caller (not wired yet; target uniqueness belongs to the wiring items).
- Failing saves: no form posts from these fragments (amount-input shows its error line with role=alert and aria-invalid, verified in the error variants).
- Direction label gap: see above.

## Findings

None blocking. Result: CLEAN.
