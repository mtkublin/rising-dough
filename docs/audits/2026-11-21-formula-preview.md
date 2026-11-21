# Frontend audit: formula preview on the recurring form (T-D-UT12-3)

Date: 2026-11-21. Skill: `frontend-visual-audit` (Playwright Chromium against the e2e scratch server and a scratch DB, never `data/budget.sqlite`).

## Scope

Routes: `/ledger` Add-entry slide-over, Repeats tab, Formula amount source (the shared `partials/recurring/_form.html`, also served by `/recurring/{id}/edit`). Two states per viewport: ok chip (`= 500.00`, one term 50% of a 1000.00 rule) and error chip (coefficient without a source). Viewports 1440x900, 1024x768, 375x812.

## Findings

| Signal | 1440 | 1024 | 375 |
|---|---|---|---|
| horizontalScroll | no | no | no |
| overflowingElements inside the form | none | none | none |
| duplicateIds | none | none | none |
| requestFailures | none | none | none |
| consoleErrors | see note | see note | see note |

- 375: `TABLE.ledger` (the ledger page behind the backdrop) reports `right > innerWidth`; it is clipped by its own scroller, causes no document scroll, and is unrelated to this change.
- Layout: the chip sits in the formula footer next to "+ Add term"; the footer now wraps (`flex-wrap`), so the note drops below the chip on narrow widths. The error text wraps inside the chip (`white-space: normal`).
- Console note: an error chip is a deliberate `422` from `POST /recurring/formula/preview` (contract unchanged); Chromium logs "Failed to load resource ... 422" for it. Triaged as expected, no JS error. Changing the status to 200 would break the route contract (`tests/contract/ledger/test_recurring.py`).

## Step 3b: behaviour contract and template logic

- No arithmetic or `float` added to templates; the amount is formatted by the existing preview partial.
- The rendered chip equals the service value: the e2e journey asserts `= 500.00` and `= 480.00` for a two-term formula (50% of 1000.00 minus 10% of 200.00), and the cycle message `formula would create a cycle via rule <id>`.
- Every failing preview shows a visible chip (`data-code` cycle / invalid_source / non_positive / empty).
- The preview never closes the edit slide-over: the request issuer is outside the `[data-close-overlay-on-success]` form (`overlay-actions.js` closes on any successful htmx request whose target sits inside such a form); the e2e cycle journey asserts the slide-over stays open and no `audit_log` row is written.
