# Audit: UR04f dialog shell static output hero (2026-11-25)

## Scope

Change: `hero.output: true` renders the handoff's `<output class="rd-dialog__amount rd-dialog__amount--static" for=...>` instead of the editable input; the dev `reconcile` variant now shows the difference (+4.29, "PLN difference") in the hero and a body field `field-actual_balance` (balance in your bank). Markup source: overlays/reconcile.html, reconcile--liability.html.

Route: /dev/shell/dialog/reconcile, opened through `htmx.ajax` into `#modal-root` from /dev/shell (the dev row menu has no reconcile item). Playwright e2e target, 1440 and 375, light and dark (4 captures).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /dev/shell/dialog/reconcile | 1440 light, dark | false | 0 | 0 | 0 | 0 |
| /dev/shell/dialog/reconcile | 375 light, dark | false | 0 | 0 | 0 | 0 |

Visual: orange band with title and close, 56px static figure "+4.29" with the "PLN difference" unit at the right, body with the bank balance field (suffix PLN) and actions (cancel, preview, [ reconcile ]). At 375 the dialog docks as a bottom sheet. Captures were taken while the open animation ran, so the 1440 capture is semi-transparent; geometry diagnostics were read from the DOM after open. Step 3b: no arithmetic, `{% set %}` or float in the macro or the dev page; the figure is a caller string. Findings: none. Status: CLEAN.
