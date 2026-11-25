# Frontend visual audit: T-UR02c error flash on the new shell

Task: T-UR02c, branch wi/ui/sourdough/UR02c. ADR-0027, ADR-0107, ADR-0143, ADR-0152.
Method: Playwright (chromium) probe over the e2e server, scratch DB only, heavy lock /tmp/ui-redesign-heavy.lock taken and released per run.
data/budget.sqlite not touched.

## Routes and states

/dev/shell, error flash through POST /dev/shell/fail/500 (a real 500 through the handlers), with and without the open "dev note" modal dialog.
1440, 1024, 375 wide, light and dark: 12 states.

## Diagnostics

| State | horizontalScroll | overflowingElements | duplicateIds | consoleErrors (excluding the deliberate 500 line) | requestFailures |
|---|---|---|---|---|---|
| all 12 states | 0 | 0 | 0 | 0 | 0 |

## Behaviour

- New-shell HTMX errors (header `X-Shell: rd`, set by app-toast.js) render `fragments/flash/error.html`: `rd-flash rd-flash--error`, the ▲ prefix and the close
  control. The 404, 409 and 500 flashes are asserted in tests/integration/web/test_errors.py; requests without the header keep `partials/_flash.html`.
- With a modal dialog open the flash is shown in a live region inside the dialog (same role and aria-live as the page region), removed when the dialog
  closes. tests/e2e/test_rd_dialog_shell.py asserts `document.elementFromPoint` at the flash centre lands inside the flash.
- Screenshots (1440 light, 375 dark) were read: the flash sits at the top of the dialog, above the band at desktop and above the bottom sheet at 375.

## Findings

None open. The page-level flash under the backdrop (UR07b F9, UR14 F1) is fixed.
