# Frontend visual audit: D1B app-owned overrides.css (2026-11-26)

Item D1B, branch `wi/ui/sourdough/D1B`, audited sha 302a8505 (base c853c36a). Skill `frontend-visual-audit` (Playwright, Chromium), scratch DB built by `tests/visual/handoff_seed.py` (base seed, fresh file), served by `tests.visual.frozen_server` at 2026-10-31 on a free port. Never `data/budget.sqlite`.

Change: `src/budget_planner/web/static/rd/app/overrides.css` (linked after `app.bundle.css` in `layouts/base.html`) holds the `.rd-dialog__error` rules (moved out of vendored `rd/css/components/dialog.css`) and the D1-b rule that keeps the hero amount's focused underline while the category picker is open.

## Routes x viewports

Routes: `/ledger`; the edit-transaction dialog opened from `/ledger` (`/transactions/11/edit`); the override dialog (`/budget/rules/12/overrides/new`, the only real source of a dialog-level `rd-dialog__error` line); `/add?when=happened&dialog=1` with and without the picker open. Viewports 1440, 1024, 375, each in light and dark (`prefers-color-scheme`): 4 routes x 6 = 24 rows. Rows that cover two states (dialog before/after submit, before/after picker) show the worst of both.

| Route | Theme width | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /ledger | light 1440 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | light 1440 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | light 1440 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | light 1440 | false | 0 | 0 | 0 | 0 |
| /ledger | light 1024 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | light 1024 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | light 1024 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | light 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | light 375 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | light 375 | false | 1 (pre-existing) | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | light 375 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | light 375 | false | 1 (pre-existing) | 0 | 0 | 0 |
| /ledger | dark 1440 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | dark 1440 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | dark 1440 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | dark 1440 | false | 0 | 0 | 0 | 0 |
| /ledger | dark 1024 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | dark 1024 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | dark 1024 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | dark 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | dark 375 | false | 0 | 0 | 0 | 0 |
| /transactions/N/edit dialog (amount 0 submit) | dark 375 | false | 1 (pre-existing) | 0 | 2 (forced 422 resource logs) | 0 |
| override dialog 422 (rd-dialog__error) | dark 375 | false | 0 | 0 | 2 (forced 422 resource logs) | 0 |
| /add?when=happened&dialog=1 (+ picker open) | dark 375 | false | 1 (pre-existing) | 0 | 0 | 0 |

"Forced 422": Chromium logs "Failed to load resource ... 422" for the intentional 422 saves (amount 0, month 13); no script errors, no CSP violations, no failed requests or non-422 4xx/5xx. `/static/rd/app/overrides.css` answered 200 `text/css; charset=utf-8` in every run.

Pre-existing overflowingElements (1 at 375, both themes): `label.rd-chip-option` right=405/417 inside the deliberate `overflow-x: auto` recents row. It is identical with `overrides.css` disabled in the page (right=405), so it does not come from this change; no horizontalScroll.

## Behaviour checks (D1B)

- Dialog-level error (override dialog, hidden month tampered to 13, POST 422): `<p class="rd-dialog__error">▲ Month: pick a month from 1 to 12</p>` visible (height 20 px, 60 px at 375 where it wraps), font-weight 500, color rgb(163, 21, 77) in light and rgb(255, 79, 139) in dark, equal to the resolved `--color-over` in both themes, at all three widths. Styled as before (PAR-B).
- Edit-transaction dialog, amount "0": the hero error line `rd-dialog__hero-error` "▲ Enter an amount above 0.00" shows (weight 500, visible). That class is not touched by D1B; the PAR-B `rd-dialog__error` line is the orphan line above (an amount error is rendered as the hero error, not the orphan line, by design in `dialog.html` `_orphans`).
- New entry dialog, picker open (`combobox-open` click, focus moves to `rd-catpick__input`, picker visible): hero height 74 px before and after at every width/theme; amount `border-bottom-width` 4 px before and after. A/B on the same page with the `overrides.css` sheet disabled: hero 74 -> 72 px and underline 4 -> 2 px, so the D1-b rule is what prevents the jump. The dialog itself grows by the picker list (658 -> 852 px at 1440, 720 at 1024, unchanged 658 at 375 where it is full-height); the hero does not move.

## Step 3b

- Swap targets: `#modal-root` and `#flash-region` are single elements after the edit and override swaps (count 1); duplicate ids re-run after each swap: 0.
- Failing saves: forced 404, 409 and 500 on POST `/transactions/*` from the edit dialog: dialog stays open and shows a visible error each time ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side..."); not left looking saved.
- Template logic: the only template change is the extra `<link rel="stylesheet">` in `layouts/base.html`; no float, `/ 100`, `* 100`, set or literal added.
- Money/rendered number: no number-rendering template changed; the amount field values (35.50 edit, 956.74 override) are service values, unchanged by this item.
- Listeners: no new HX-Trigger events.

## Findings

None.

## Screenshots

Under the scratchpad `D1B/` directory (not committed), `<theme>_<width>_{ledger,edit_invalid,override_error,add_before,add_picker}.png`; viewed: `light_1440_override_error.png` (override dialog with the pink `▲ Month: pick a month from 1 to 12` line, dialog captured mid-transition over the dimmed ledger, no layout break) and `dark_375_add_picker.png` (picker sheet open over the new-entry dialog, thick underline under the amount, hero in place). Numbers come from DOM measurements.
