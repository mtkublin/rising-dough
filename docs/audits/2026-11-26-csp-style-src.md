# Frontend visual audit: CSP (style-src nonce only; htmx attributesToSettle without `style`)

Change (T-UR16, ADR-0113): CSP `style-src 'self' 'nonce-...'` (no `'unsafe-inline'`); `layouts/base.html` htmx-config `attributesToSettle: ["class","width","height"]`; category hue rules moved from `<style nonce>` blocks to `<span hidden data-color-rules>` fed by `rd/app/color-rules.js` into one constructed stylesheet (CSSOM). Audited at sha ddee6ac9 with the `frontend-visual-audit` skill (Playwright, chromium) on the handoff base seed (`tests/visual/handoff_seed.py`, frozen date 2026-10-31) in a scratch DB, never `data/budget.sqlite`. Screenshots (scratch, not committed) in the session scratchpad `csp/out/`: `<width>_<route>__<state>.png`, `hue_<width>_*.png`.

Served header (verified on `/today`): `default-src 'self'; script-src 'self' 'nonce-..'; style-src 'self' 'nonce-..'; ...`. Positive control: an inline `style` attribute inserted at runtime is refused with the CSP console error (so the policy is live and the page is clean only because nothing uses inline styles).

## Diagnostics (route x viewport)

Each cell: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures. Zero `[style]` attributes in the DOM on every route. No console message contained "Content Security Policy" or "violates" in any row.

| Route | 1440 | 1024 | 375 |
|---|---|---|---|
| /today | no/0/0/0/0 | no/0/0/0/0 | no/1*/0/0/0 |
| /ledger (+ tabs planned, recurring, row menu, new-entry dialog) | no/0/0/0/0 | no/0/0/0/0 | no/0/0/0/0 |
| /plan?tab=budget | no/0/0/0/0 | no/0/0/0/0 | no/0/0/0/0 |
| /plan?tab=year | no/0/0/0/0 | no/0/0/0/0 | no/0/0/0/0 |
| /accounts (+ reconcile dialog) | no/0/0/0/0 | no/0/0/0/0 | no/0/0/0/0 |
| /settings?tab=categories | no/0/0/0/0 | no/0/0/0/0 | no/3*/0/0/0 |
| /settings?tab=fx | no/0/0/0/0 | no/0/0/0/0 | no/3*/0/0/0 |

\* 375 only, no page-level horizontal scroll. `/today`: decorative `pre.rd-hero__loaf` (right 399) inside `.rd-hero` with `overflow: hidden` (clipped by design). `/settings`: three `a.rd-tabs__tab` (right 403/504/581) inside `.rd-tabs` with `overflow-x: auto` (scrolling tab strip, visible in the screenshot as a cut-off "prefe..." tab). Both are clipped by their own scroll/clip container, not caused by this change (the diff touches no hero or tabs rule); the 375 diagnostics of these routes are unchanged from the earlier sourdough audits.

## Interactive checks

- Row menu (`/ledger`, popover): at 1440 popover top = trigger bottom + 4 (330.4 vs 326.4), right edge = trigger right (1336); at 1024 same offsets (right 976); at 375 it is the bottom action sheet (left 0, right 375). Position set through CSSOM by `row-menu.js` (`style` attribute is allowed to be set from script; no CSP error). Identical geometry on first open and after an HTMX swap (planned tab, back to actual).
- Ledger tab switch actual / planned / recurring: `#ledger-table` count 1 after each swap, duplicate ids 0, no horizontal scroll.
- New-entry dialog (`/ledger`) and reconcile dialog (`/accounts`): open in `#modal-root` at all three widths, duplicate ids 0.
- Category colours: preset swatches on `/settings?tab=categories`: 37 swatch elements, 0 transparent. Custom hues (scratch DB: three expense categories set to `#12ab9c`, `#c2185b`, `#7a5af8`): every `[data-color^="c-"]` element has `--cat` resolved (ledger 4/4, settings 6/6, today 1/1, at 1440/1024/375) and the ledger count stays 4/4 after the HTMX tab swap round trip (the module re-applies after `htmx:afterSwap`). Pills render with the custom hue (viewed `hue_375_settings_categories.png`, `1440_ledger__menu-after_swap.png`).

## Step 3b

- Swap targets: `#ledger-table`, `#ledger-tabs`, `#modal-root` unique before and after swaps; no duplicate ids after any swap or dialog open.
- Failing saves (reconcile dialog, POST forced to 404 / 409 / 500 via `page.route`, 1440): visible error banner each time ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again."), dialog stays open, not shown as saved. A forced bare 422 with a non-HTML body shows nothing (artificial; real 422 inline errors are covered by the BUGA audit).
- Templates: `rg "float|/ 100|\* 100"` over the templates changed by this item: no hits; the item only replaces `<style nonce>` blocks by a data attribute.
- Rendered numbers and money filters: no number-producing template or service changed; spot value on `/ledger`: spent this period 19,417.18 PLN, row amounts unchanged from the handoff seed. Not re-checked for a JPY account (no template money path touched).
- Listeners: the `htmx:afterSwap` listener in `color-rules.js` is the only one added; no new `HX-Trigger`.

## Findings

None blocking. Triaged: the 375 overflowing-element counts above are elements clipped inside their own `overflow` containers (page scroll width equals the viewport).

Result: CLEAN.
