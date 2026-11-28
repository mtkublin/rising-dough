# ADR-0143: One HTMX Event and Toast Contract; Error Flashes Always Swap

- **Status**: Accepted
- **Date**: 2026-11-21
- **Relates to**: [ADR-0002](0002-web-stack-fastapi-htmx-jinja.md), [ADR-0113](0113-csp-compatible-frontend.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0141](0141-one-amount-parser-and-bounded-request-parameters.md)
- **Finding**: Q-037 (E-01), Q-038 (A-18, E-02, E-07); task T-Q236; resolves OQ-27 (default, pending operator confirmation)

## Context

htmx 2 does not swap 4xx/5xx. `web/errors.py` builds an out-of-band flash for 404/409/500, but only 422/429 were forced to swap, so failed saves and stale-row conflicts were silent. Four of the seven server events (`balance-stale`, `budget-stale`, `today-stale`, `settings-categories-stale`) had no listener, routers hand-built `HX-Trigger` JSON in five places, and the toast payload used `kind` in one router and `variant` in the rest (the client reads `variant`).

## Decision

1. `web/htmx.py` is the only emitter. It owns `Event` (a `StrEnum` of the wire names), `toast_payload(variant, message, *, undo_url, undo_payload)` and `trigger(response, *events, toast=None)`. Routers never write the `HX-Trigger` header or a `*-stale` literal. The toast payload key is `variant`.
2. Every `*-stale` event has a listener: a region that shows derived data declares `hx-trigger="<event> from:body"` and re-fetches itself (`hx-get` of the current page plus `hx-select` of its own id). Today hero and upcoming (`today-stale`), accounts hero (`balance-stale`), budget pace and summary (`budget-stale`), settings category list (`settings-categories-stale`), ledger and forecast as before.
3. One global `htmx:beforeSwap` handler in `static/js/app-init.js` handles every 4xx/5xx: a response that is the flash partial swaps out of band only (`swapOverride = "none"`, nothing in the originating target is cleared); a 422/429 form re-render swaps as before; any other error shows a generic status message in `#flash-region` (one region since the 2026-11-26 amendment). `htmx:sendError` and `htmx:timeout` show a connection message. `users-admin.js` no longer carries its own 409 rule.
4. The undo reload after a toast `Undo` fires only when the undo request succeeded.
5. Guard G12 (`test_htmx_contract.py`) is strict, with no allowlist: every emitted `Event` has a listener, every listener has an emitter, every `Event` member is emitted, no `HX-Trigger` header or `*-stale` literal exists outside `web/htmx.py`, static `hx-target` ids exist.

Amendment 2026-11-26 (T-UR00b, operator option D9-A): one flash region. The shell has a single live region, `#flash-region` (`role="status"`, `aria-live="polite"`), as the handoff does (`today--flash`: saved and error flash 8 px apart, the region's own gap). `#flash-region-assertive` is removed (`layouts/base.html`, `web/errors.py`, `web/users_admin.py` `FLASH_REGION`, `fragments/flash/error.html`, `app-toast.js`). Accessibility: the error flash box keeps its own `role="alert"` (also the client-built `flashBox`), so a screen reader still announces an error assertively; only the container is polite. `show()` in `app-toast.js` replaces only a previous flash of its own kind (error or saved), so both sit side by side. The in-dialog region (a modal sits in the top layer) is `role="status"`; its error box carries the alert. Tests locate the region through `tests/ui_map/shell.py` `flash_region`.

Amendment 2026-11-28 (DUPERR, T-UR16 sweep finding 3): one visible message per failure. While a modal dialog is open, an error belongs in the dialog (in context): `app-toast.js` routes a `toast` event with `variant: "error"` through the in-dialog flash (`show()`), and drops it when that flash already carries the same text. Page-level actions (no open dialog) keep the toast. Chosen client-side because the client alone knows whether a dialog is open; the server keeps emitting one payload shape (`web/htmx.py` unchanged) and success/info toasts (with undo) still appear above an open dialog. Server error responses (404/409/500) never carried a toast, only the flash partial, so the one place a duplicate could arise is a response with both; that is now closed.

## OQ-27 default (taken 2026-11-21, pending operator confirmation)

After a `*-stale` event the affected panel re-fetches, so no stale totals remain until reload. The undo reload fires only on a successful undo.

## Consequences

- A failed save is always visible. The wire names are unchanged, so templates and tests keep their event strings.
- A new event needs an `Event` member, an emitter and a listener in the same change or the guard fails.
