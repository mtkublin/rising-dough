# Audit: UR04f dialog shell static output hero (2026-11-25)

## Scope

Change: `hero.output: true` renders the handoff's `<output class="rd-dialog__amount rd-dialog__amount--static" for=...>` instead of the editable input; the dev `reconcile` variant now shows the difference (+4.29, "PLN difference") in the hero and a body field `field-actual_balance` (balance in your bank). Markup source: overlays/reconcile.html, reconcile--liability.html.

Route: /dev/shell/dialog/reconcile, opened through `htmx.ajax` into `#modal-root` from /dev/shell (the dev row menu has no reconcile item). Playwright e2e target, 1440, 1024 and 375, light and dark (6 captures). Each capture waits for `dialog#dev-reconcile[open]`, then for `getAnimations({subtree:true}).length === 0`, plus 500 ms margin; diagnostics are read from the DOM at that point.

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /dev/shell/dialog/reconcile | 1440 light, dark | false | 0 | 0 | 0 | 0 |
| /dev/shell/dialog/reconcile | 1024 light, dark | false | 0 | 0 | 0 | 0 |
| /dev/shell/dialog/reconcile | 375 light, dark | false | 0 | 0 | 0 | 0 |

Captures viewed (after the animation): 1440 light, 1024 dark, 375 light. The other three (1440 dark, 1024 light, 375 dark) were checked through the DOM diagnostics only (identical values: output text "+4.29", unit "PLN difference", output font 56px, only input `field-actual_balance`).

Compared with overlays/reconcile.html: orange/peach band with title "reconcile Checking" and round close button; 56px static figure "+4.29" bottom-left of the hero with "PLN difference" bottom-right; body field "balance in your bank" with the PLN suffix; actions row quiet cancel, outlined preview (dev-only extra), primary [ reconcile ]. Same band, hero row, output classes and ids as the handoff (asserted by the parity tests against reconcile.html and reconcile--liability.html). Light: peach band, orange primary. Dark: orange band, lime primary (handoff dark tokens). At 375 the dialog docks as a bottom sheet; the cancel button is not visible in the 375 capture (existing rd-dialog sheet CSS, untouched by this item; not verified against the handoff sheet).

Step 3b: no arithmetic, `{% set %}` or float in the macro or the dev page; the figure is a caller string. Findings: none. Status: CLEAN.
