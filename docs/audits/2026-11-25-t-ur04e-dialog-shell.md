# Frontend audit: T-UR04e shared dialog shell and row-menu item kinds

Task: T-UR04 follow-up (wave 6a carve-out, ADR-0107, ADR-0130 section 7). Branch wi/ui/sourdough/UR04e.
Method: frontend-visual-audit skill (Playwright/Chromium, explicit viewports, real login through the e2e `page` fixture) against a migrated scratch DB, uvicorn on an ephemeral 127.0.0.1 port; light and dark through `emulate_media(color_scheme)`. Heavy lock /tmp/ui-redesign-heavy.lock taken and released. Screenshots in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR04e/shots/ (viewed: light-1440-invalid, light-1024-delete, dark-375-sheet, dark-375-menu), raw diagnostics in .../UR04e/audit.json.

## Routes x viewports

Route: /dev/shell with the dev row menu open, then each dialog variant opened from the menu (standard, invalid, blocked, delete/confirm; sheet below md only because its menu item is phone-only). 32 captures (light and dark x 3 viewports).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /dev/shell (menu + 4 dialogs) | 1440 light, dark | false | 0 | 0 | 0 (see note) | 0 |
| /dev/shell (menu + 4 dialogs) | 1024 light, dark | false | 0 | 0 | 0 (see note) | 0 |
| /dev/shell (menu + 5 dialogs) | 375 light, dark | false | 0 | 0 | 0 (see note) | 0 |

Note on console: the only console entries in the run are the browser's own "Failed to load resource: 422" line, one per opening of the `invalid` variant (6 in total, one per light/dark x viewport). That variant answers a deliberate 422 through `invalid_dialog_response` (the thing under test); there is no JS error, no failed request and no htmx target error. Every other variant produced no console entry.

## Visual compare against the handoff overlays

- Standard (new-account, new-account--error): band with title, round close button, hero amount with the PLN unit and the hero note or the `▲` hero error; body with field, actions row (quiet cancel left of the orange primary). 422: the rose error summary ("2 fields need attention", two links) above the field, `▲` per-field message. Deviation: no handoff overlay shows a summary (new-entry--error and new-account--error have inline errors only); the summary reuses the full-page pages/errors/422.html treatment and is recorded in derived.md.
- Confirm (delete-account, archive-category): small centred card, title, text, quiet cancel plus the rose-outlined destructive submit. Blocked: same card, link action plus `[ ok ]`, no form.
- Phone sheet (new-entry--phone-sheet) at 375: same markup, docked to the bottom edge full width, orange band with signed hero (−35.50 PLN), lime primary filling the row, grabber-less sheet as in the handoff. Dark theme tokens apply.
- Row menu at 375 (row-menu--*): bottom action sheet with grabber, head (title and sub), 52 px rows, destructive `delete` in rose, `cancel` last. Desktop: anchored popover; the phone-only item is hidden at 1440 and 1024 (asserted in e2e).

## Step 3b

- Swap targets: `#modal-root` exists once before and after each open; menu items target it (`hx-target="#modal-root"`); the dialog form posts back to `#modal-root`.
- No `{% set %}`, arithmetic, float or currency literal in fragments/dialogs/dialog.html, fragments/menus/row-menu.html or pages/dev/* (the unit string is a caller argument; guard G9 green).
- Failing saves visible: standard and invalid variants POST to a route that answers 422 and re-render the dialog with the summary (e2e `test_submitting_the_standard_form_shows_the_422_summary`); confirm POST answers `saved_response` with the flash. No money values rendered from a service.
- IDs after each swap: no duplicates (diagnostic re-run with every dialog open).
- HX events: no custom HX-Trigger added; `saved_response` and `invalid_dialog_response` unchanged.

## Findings

None. Status: CLEAN.

## UR04f: static output hero (reconcile variant)

Change: `hero.output: true` renders the handoff's `<output class="rd-dialog__amount rd-dialog__amount--static" for=...>` instead of the editable input; the dev `reconcile` variant now shows the difference (+4.29, "PLN difference") in the hero and a body field `field-actual_balance` (balance in your bank). Markup source: overlays/reconcile.html, reconcile--liability.html.

Route: /dev/shell/dialog/reconcile, opened through `htmx.ajax` into `#modal-root` from /dev/shell (the dev row menu has no reconcile item). Playwright e2e target, 1440 and 375, light and dark (4 captures).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /dev/shell/dialog/reconcile | 1440 light, dark | false | 0 | 0 | 0 | 0 |
| /dev/shell/dialog/reconcile | 375 light, dark | false | 0 | 0 | 0 | 0 |

Visual: orange band with title and close, 56px static figure "+4.29" with the "PLN difference" unit at the right, body with the bank balance field (suffix PLN) and actions (cancel, preview, [ reconcile ]). At 375 the dialog docks as a bottom sheet. Captures were taken while the open animation ran, so the 1440 capture is semi-transparent; geometry diagnostics were read from the DOM after open. Step 3b: no arithmetic, `{% set %}` or float in the macro or the dev page; the figure is a caller string. Findings: none. Status: CLEAN.
