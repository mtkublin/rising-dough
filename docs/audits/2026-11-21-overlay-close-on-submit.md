# Frontend audit: overlay closes only on its own submit (T-D-UT12-1)

Date: 2026-11-21. Change: `static/js/overlay-actions.js` (no template or CSS change).

Routes checked: `/ledger?view=actual` with the transaction edit slide-over open and the amount typed (limit preview fired), at 1440, 1024 and 375 px (Playwright Chromium, scratch DB).

| Viewport | horizontalScroll | overflowing slide-over elements | duplicateIds | consoleErrors | requestFailures | slide-over still open after preview |
|---|---|---|---|---|---|---|
| 1440 | false | 0 | none | 0 | 0 | yes |
| 1024 | false | 0 | none | 0 | 0 | yes |
| 375 | false | 0 | none | 0 | 0 | yes |

Behaviour contract (Step 3b): no template changed, so no new arithmetic or float in templates; the Save path still closes the overlay and the DB row carries the exact minor units (4567), asserted in `tests/e2e/journeys/test_edit_delete.py::test_limit_preview_does_not_close_edit_slideover_before_save`.

Other `data-close-overlay-on-success` users (reconcile modal, planned and recurring promote, recurring override, planned/recurring edit forms) all put the attribute on the form that carries its own `hx-post`; the e2e journeys for them pass (33 passed, 1 pre-existing skip).

Findings: none.
