# Frontend visual audit: T-UR13 settings (categories, currency and FX, preferences, category dialogs)

Task: T-UR13, branch wi/ui/sourdough/UR13. ADR-0027, ADR-0107, ADR-0150, ADR-0152.
Method: frontend-visual-audit skill (Playwright, chromium), second heavy slot /tmp/ui-redesign-heavy-2.lock taken and released around each run.
Scratch data only: a copy of data/demo.sqlite (26 categories, four with non-preset custom hues, plus two cached FX rates added: EUR to PLN 4.2345
and USD to PLN 3.9). data/budget.sqlite not touched.

## Routes and states

/settings?tab=categories, /settings?tab=fx (with two cached rates), /settings?tab=prefs; dialogs opened from the categories page: new, new filled
(name, income, sky swatch), new error (whitespace name, server 422), edit (first row), archive (first row). Light and dark, each at 1440, 1024 and 375:
48 diagnostic rows (8 states x 3 widths x 2 themes).

## Diagnostics

| State | horizontalScroll | duplicateIds | consoleErrors | requestFailures | HTTP >= 400 (other than the deliberate 422) | overflowingElements |
|---|---|---|---|---|---|---|
| all 8 states, 1440 and 1024, both themes | 0 | 0 | 0 | 0 | 0 | 0 |
| all 8 states, 375, both themes | 0 | 0 | 0 | 0 | 0 | 2 (see below) |

Every id-based hx-target (#modal-root, #category-N, #settings-categories) matches exactly one element. The browser logs the deliberate 422 of the
failing save as a console line ("Failed to load resource ... 422"); it is the expected behaviour, filtered from the console count.

Overflowing elements at 375: two `a.rd-tabs__tab` (the security tab, and users for an admin) sit right of the viewport. They are inside `.rd-tabs`
(`overflow-x: auto`), so the document has no horizontal scroll. The handoff board `pages/settings/categories.html` measured the same way gives three
overflowing tabs at 375 (categories, security, users), so this is handoff parity (the strip scrolls sideways on a phone), not a finding.

## Comparison with the handoff boards (settings/categories, currency-fx, preferences, overlays new-category*, edit-category, archive-category)

Screenshots of the boards and the app were compared at 1440 and 375 in light, and the app also in dark. Hero band, tab pills, `+ new category`, income
anchor card, group titles with counts, chip and colour-dot rows, `edit` and `archive` buttons, `locked` on system rows, the FX card and the Appearance
and Workspace cards, the dialog band, name field, direction segmented control, colour radios and swatch grid, preview row, the 422 summary above the
body with the inline `▲ name required` under the field, and the confirm dialog match in structure, spacing and type. Phone: the dialogs are a bottom
sheet, the rows wrap their colour text under the chip.

Known and accepted (derived.md rows added): the preview chip is rendered by the server and does not follow typing; stored hues outside the ten
swatches keep their own generated chip colour; the FX rates table is derived (the board shows only the empty state); the tab strip carries tab roles.

## Findings

1. Shell, low, not mine: the topbar `settings` link has no current-page state on /settings (the board marks it as the active, black pill). The base
   layout (`layouts/base.html`, owned by the shell item) has no `nav_current` value for settings. Report for T-UR02 / the wave tester.
2. Full-page screenshots of an open dialog catch it mid fade-in (the dialog looks translucent); a viewport screenshot after the transition shows the
   final state. Not an app issue.

## Step 3b

- Templates (pages/settings/*, fragments/nav/settings-tabs, fragments/rows/category-row): rg for `style=`, `{% set`, `float`, `/ 100`, `* 100`: no hits.
  The row colour classes come from `settings_view.category_row_view` (`category_colors.category_color`); the group counts, the usage text
  ("1 rule", "1 planned") and the dialog title are view-model values.
- Rendered equals service: FX page prints `EUR → PLN  2026-11-20  4.2345` and `USD → PLN  2026-11-20  3.9` exactly as cached (the integration test
  asserts `4.25` for a stored `4.25`); Preferences prints the settings values `PLN` and `Europe/Warsaw`; the categories page counts (Expense 16,
  Income 5, System 2 for the demo copy) equal the rows listed under each heading.
- A failing save shows a visible error: whitespace name on the new dialog returns 422, the dialog stays open and shows the error summary
  ("1 field needs attention, Name: name required", role alert) and the inline `▲ name required` under the name field with `aria-invalid`
  (`error_visible` true in all 6 viewport and theme runs).
- Archive: the 204 closes the confirm dialog through the `dialog-close` event (e2e `test_archive_category_closes_the_dialog_shows_undo_then_restore`),
  the list refetches on `settings-categories-stale`, the toast offers undo and undo restores the row.
