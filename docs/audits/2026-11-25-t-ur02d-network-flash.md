# Frontend audit: network-failure flash on the new shell (T-UR02d)

Change: `static/rd/js/app-toast.js`, `htmx:sendError` handler (T-UR02, T-UR25, ADR-0143). Hero refreshes
(`hero=1`) only mark the hero stale; requests from inside a form return (offline.js shows the offline state
at the top of the form); everything else raises "Could not reach the server. Check your connection and try
again." in `#flash-region-assertive`.

Branch `wi/ui/sourdough/UR02d` at 76972ee3. Run with the `frontend-visual-audit` skill (Playwright, Chromium)
against `data/demo.sqlite` copied to a scratch file, own port, network cut with `context.set_offline(True)`.
Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/<vp>__<scenario>_<n>.png`.

## Standard sweep (online)

Routes `/today`, `/ledger`, `/plan`, `/settings` at 1440, 1024, 375 (12 rows).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today | 1440 | false | 0 | 0 | 0 | 0 |
| /today | 1024 | false | 0 | 0 | 0 | 0 |
| /today | 375 | false | 1 (`pre.rd-hero__loaf`, decorative art clipped by `.rd-hero` overflow hidden) | 0 | 0 | 0 |
| /ledger | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | false | 1 (`a.rd-tabs__tab`, inside `nav.rd-tabs` overflow-x auto strip) | 0 | 0 | 0 |
| /plan | 1440 / 1024 / 375 | false | 0 | 0 | 0 | 0 |
| /settings | 1440 | false | 0 | 0 | 0 | 0 |
| /settings | 1024 | false | 0 | 0 | 0 | 0 |
| /settings | 375 | false | 2 (`a.rd-tabs__tab`, inside `.rd-tabs` overflow-x auto strip) | 0 | 0 | 0 |

The three 375 overflowing entries are intentional scroll or clip containers that exist independent of this
JS-only change; no page-level horizontal scroll. Triaged, not caused by T-UR02d. Single `#flash-region`,
`#flash-region-assertive`, `#toast-root`, `#modal-root`, `#main` on every route (swap targets unique).

## Offline scenarios (network cut after load)

Counts per scenario at 1440, 1024 and 375 (identical across viewports unless noted). "flash" = boxes in
`#flash-region-assertive`; "polite offline" = offline state in `#flash-region`; "form offline" = offline state
inside a form.

| Scenario | Trigger | flash | polite offline | form offline | Result |
|---|---|---|---|---|---|
| today_segment | upcoming "7 days" (non-form hx-get) | 1 | 1 | 0 | flash shown, no overlap |
| today_promote_link | promote link (non-form, modal fetch) | 1 | 1 | 0 | same |
| ledger_new_entry | `[ new entry ]` | 1 | 1 | 0 | same |
| plan_override_menu_item | row menu "override" | 1 | 1 | 0 | same |
| settings_new_category / settings_category_edit | modal fetch links | 1 | 1 | 0 | same |
| today_form_afford | afford form input | 0 | 0 | 1 | in-form state only |
| ledger_filter_form | filter form (the ledger filters are a form) | 0 | 0 | 1 | in-form state only |
| ledger_row_edit_in_bulk_form | row edit link (inside the bulk form) | 0 | 0 | 1 | in-form state only |
| settings_form_anchor | income-anchor form | 0 | 0 | 1 | in-form state only |
| dialog_hero_refresh | account select change in new-entry dialog | 0 | 0 | 1 | no flash; hero unit shows an em dash; in-form state shown by offline.js |
| dialog_tab_switch | happened/planned/repeats (inside dialog form) | 0 | 0 | 1 | in-form state only |
| dialog_save_form | submit new-entry dialog | 0 | 0 | 1 | in-form state only, no duplicate flash |

Repeating the same action a second time keeps exactly 1 flash and 1 offline state (no stacking), in every row.
Offline-phase diagnostics (horizontalScroll false, duplicateIds none) hold with the flash and offline state
visible at all three viewports.

Check 4 (today_segment, then online "all" succeeds): the offline state is removed by offline.js, but the
assertive flash stays (see findings).

consoleErrors during forced offline (expected, listed separately): 6 per offline action (3 `Failed to load
resource: net::ERR_INTERNET_DISCONNECTED` plus HTMX send error logs), 12 for the filter and hero scenarios
(two requests); requestFailures 2 or 4 respectively. Online consoleErrors and requestFailures: 0 in all
scenarios.

## Step 3b

- Swap targets: unique before and after the offline swaps (counted in the sweep and offline diagnostics).
- No templates changed in this item; the change is JS. No arithmetic, `float` or literals introduced.
- Failing saves visible: network failure of the dialog save shows the in-form offline state (no silent
  failure, no duplicate flash). 404/409/500 handling was not touched by this change.
- Duplicate ids after swaps: none. Listeners: `htmx:sendError` handled by offline.js and app-toast.js.
- Scratch data only, no write to `data/budget.sqlite`.

## Findings

1. Behavior, low-medium: non-form failures show two red boxes (the "You're offline ... retry now" state in
   `#flash-region` and the "Could not reach the server" flash right under it). They do not overlap, but the
   message is duplicated and they push the page down by about 190 px at 1440 and 1024 and about 245 px at 375
   (`1440__today_segment_1.png`, `375__today_segment_1.png`). Decide whether non-form requests should show
   only one of them.
2. Behavior, low: the assertive flash is not cleared by a following successful request, while the offline
   state is (check 4, `375__today_segment_3_success.png`; the flash stays until dismissed with its close
   button). Same persistence as other error flashes.
3. Note, not a defect of this change: at 375 the `[ new entry ]` button is hidden (`display: none` below the
   mobile breakpoint), so the dialog scenarios were opened by script. Ledger filters, bulk-form row edit and
   dialog tabs are inside forms, so they get only the in-form state per the new rule.

Verdict: FINDINGS (1 and 2 for the orchestrator to triage; diagnostics clean apart from the expected offline
console and request failures).
