# Frontend visual audit: N1 near-pass fixes (2026-11-25)

Item N1, branch wi/ui/sourdough/N1, sha 391d999, base ui/sourdough (f33072c). Skill: frontend-visual-audit
(headless Chrome via Playwright, frozen clock 2026-10-31 as in tests/visual/conftest.py). Data: scratch DB built by
tests/visual/handoff_seed.py (modifiers recurring-board, settings-categories), never data/budget.sqlite. Comparison server on
MAIN (f33072c) with a copy of the same DB.

Changed templates: fragments/today/afford-result.html, fragments/fields/field.html, pages/accounts/dialog-account.html,
pages/settings/category-dialog.html, recurring dialog titles (rule description).

## Routes x viewports (1440 / 1024 / 375)

Pages: /today, /ledger, /ledger?view=recurring, /plan, /plan?tab=year, /accounts, /settings, /settings?tab=categories,
/settings?tab=fx, /settings?tab=prefs, /settings/users.
States: /today afford valid (50), over (999999), invalid (abc then Enter); new-category dialog (blank name 422, duplicate
Takeaway 422); new-account dialog (blank name 422, XYZ currency 422); recurring 1 and 2 edit / promote / override dialogs;
transaction 1 edit, planned 1 edit, new entry (happened) dialogs.

## Diagnostics (horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures)

| Route / state | 1440 | 1024 | 375 |
|---|---|---|---|
| /today, afford valid/over/invalid | false/0/0/0/0 | false/0/0/0/0 | false/1/0/0/0 |
| /ledger | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /ledger?view=recurring (+ recurring dialogs, planned edit) | false/0/0/0/0 | false/8/0/0/0 | false/0 to 2/0/0/0 |
| /plan | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /plan?tab=year | false/0/0/0/0 | false/8/0/0/0 | false/8/0/0/0 |
| /accounts and new-account dialog | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /settings (all tabs), /settings/users, category dialog | false/0/0/0/0 | false/0/0/0/0 | false/3/0/0/0 |
| txn edit / new entry dialogs | false/0/0/0/0 | false/0/0/0/0 | false/1 to 2/0/0/0 |

horizontalScroll=0 and duplicateIds=0 everywhere, requestFailures=0 everywhere. overflowingElements are inner scroll
containers only (year table, recurring table actions column at 1024, settings tab strip, hero loaf pre and chip-option
labels at 375); the counts are identical on MAIN (same server, same DB), so pre-existing and not caused by N1.
consoleErrors=0 on every load and HTMX swap; the only console lines are the browser's "Failed to load resource ... 422"
for the four deliberately forced 422 saves (same on MAIN).

## Findings checked

- Field macro: dup-Takeaway 422 now has aria-invalid="true", aria-describedby="field-name-error", visible error
  "A category with this name already exists", and required still present (MAIN: aria-invalid null, required false). Blank name:
  summary "Some fields need fixing: Name" visible. Account blank name and XYZ currency: aria-invalid, describedby, visible
  "Name is required" / "Unknown currency code", required kept.
- Glued attribute scan (HTML parser plus regex over 34 URLs listed in the task): no `requiredaria-invalid` or any glued attribute
  name; the render shows `required >`. Pre-existing, identical on MAIN: a closing quote directly followed by the next
  attribute (hx-target/hx-swap/hx-confirm on ledger row actions, `value="..."required` on promote dialogs,
  `min="1"max="31"value="1"` on recurring edit). Browsers parse these; triaged, not N1.
- Recurring dialog titles: "edit recurring rule · Fixed Costs", "promote · Fixed Costs", "override occurrence · Fixed Costs"
  (rule description; MAIN shows "Fixed costs").
- Afford: one #afford-result at all times; valid "per day becomes 133.99 (down 7.14)", over "per day becomes -142,715.87 ·
  999,011.07 over"; invalid input (Enter) shows "Enter an amount, like 250.00" in the output; /today?amount=abc shows
  aria-invalid + #afford-error. Minor, pre-existing on MAIN: the live (typing) 422 path leaves #afford without aria-invalid.

## Step 3b

1. Swap targets: every hx-target selector on /settings?tab=categories and /accounts matches exactly one element.
2. Failing saves: forced 404, 409, 500 on POST /categories and POST /accounts at 1440 and 375: dialog stays open and a
   visible error is shown each time ("That item was not found...", "That item changed in the meantime...", "Something went
   wrong on our side...").
3. rg for float, / 100, * 100 and set blocks in the four changed templates: none.
4. Money formatting: afford figures go through the view model (PLN base). No JPY check needed (no money markup changed).
5. Rendered = service: today_data.afford_panel on the scratch DB gives 133.99 / 7.14 and -142,715.87 / 999,011.07 / 141.13,
   equal to the page text.
6. No duplicate ids after swaps (diagnostic re-run after each dialog open and 422).

## Screenshots

Captured under the scratchpad (shots/<vp>__<name>.png); viewed 1440__afford_over.png and 375__cat_422_dup.png: no clipping,
error line visible under the name field, dialog fits the viewport.

Result: CLEAN (non-zero overflowingElements are pre-existing on MAIN).
