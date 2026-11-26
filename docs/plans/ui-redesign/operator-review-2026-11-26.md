# Operator review, 2026-11-26

Source: explore drill run 45874586774 on ddab3a17. The operator's list is verbatim (typographic quotes normalised to straight quotes). Tasks are in [tasks.md](tasks.md).

## Operator's list

- **R1** "No accounts view - the new account button doesn't work, redirects to an empty page instead (the generic one on the right does work properly though)"
- **R2** "After adding a new income category - it only appears in the income anchor drop down after a reload"
- **R3** "New entry - > category picker -> can't select anything via mouse-click, only arrows + enter from keyboard work. Works on mobile though. Recent categories work both on desktop and mobile."
- **R4** "Plan/budget - currently we only have "override" option, which might be misleading. Imagine someone comes to the page for the 1st time, has some categories created, none with budget (as it's default) and the only thing they see is "override". This does not make me think "this is how I can set the default budget". Think how we can tackle that."
- **R5** "Plan/year - clicking on a cell in the grid allows inline editing, but the only thing it can do is set a one-off override. There's no option to change the month budget every year, nor the default. For the unbudgeted categories it works fine (an overlay appears). Think how can be done from the best UX perspective possible."
- **R6** "Plan/budget -> month picker - clicking arrows automatically loads the page with the same month but in previous/next year (depending on the arrow). I'd expect it to just switch the picker view (i.e. change the year in picker, but display the same months to select) and would only take effect if a user selects a month from this new view."
- **R7** "New entry -> repeat -> formula - no matter what I put in I get "▲ formula resolved to a non-positive amount", sometimes even a double warning, recurring payments not usable atm. Weirdly enough if I input a negative percentile value the warning disappears, but then the percentile validation fails due to negative value (as expected). Toggling between +/- for the rule - doesn't have effect on that warning"
- **R8** "Not necessarily an issue - after promotion a planned payment stays in Ledger, just marked as "promoted" without the "Promote" button. Is this expected? How long do the promoted transactions stay?"
- **R9** "Account types - when editing and Account it's currently possible to toggle between asset/liability, even though the account already exists. Don't see how that's useful and opens up a lot of unplanned and potentially buggy behaviour. Disable toggling that for existing account (both frontend and backend level)"
- **R10** "In mobile mode - clicking some fileds (e.g. how much can I spend in Today) auto-zooms the page, which I personally find annoying. Would be good to turn it off everywhere"
- **R11** "In mobile mode - some views are squeezed which forces them to the next row or generally messes up the formatting. Examples: new entry -> repeat -> formula - the category picker gets moved to the row below. Budget override - scope selector also doesn't look too good. Probably more examples of that, couldn't have gone through all. Generally this touches overlays"
- **R12** "In mobile mode - Ledger/Filter - from/to overlap and overflow to the left"
- **R13** "A few modes in mobile view (e.g. plan/year, plan/forecast) need to be scrolled horizontally to view in full. I'm thinking that all of such instances require a proper redesign with mobile focus, we can't simply squeeze in whatever is in desktop view there. Not necessarily to fix now, could be handled as a follow up."

## Triage

| id | item | class | task | status |
|---|---|---|---|---|
| R1 | New account button redirects to an empty page | bug | T-UR52 | open |
| R2 | New income category missing from the anchor dropdown until reload | bug | T-UR53 | open |
| R3 | Category picker ignores mouse clicks on desktop | bug (likely regression of WEBKIT bea9ce19 combobox.js) | T-UR54 | open |
| R4 | Plan/budget: make setting the default budget discoverable | design decision (proposal pending) | T-UR55 | decided |
| R5 | Plan/year: cell edit scopes (one-off, every year, default) | design decision (proposal pending) | T-UR56 | decided |
| R6 | Month picker arrows change the picker year only | spec change + fix | T-UR57 | open |
| R7 | Recurring formula always warns non-positive amount | bug | T-UR58 | open |
| R8 | Answer: promoted planned payments in Ledger | question (answer pending) | T-UR59 | decided |
| R9 | Account kind read-only after creation (UI and server) | spec change + fix | T-UR60 | open |
| R10 | No auto-zoom on input focus on touch widths | spec change + fix (inputs >= 16px on touch widths; do NOT disable pinch zoom: a11y) | T-UR61 | open |
| R11 | Mobile overlays squeezed (formula row, override scope) | bug | T-UR62 | open |
| R12 | Mobile ledger filter from/to overlap | bug | T-UR63 | open |
| R13 | Mobile-first redesign of wide views (plan/year, plan/forecast) | follow-up (designer change request: mobile-first redesign of wide views; not in this release) | T-UR64 | deferred |

## Decisions (2026-11-26)

Recorded from the operator's interactive session on 2026-11-26. The requirement lines are in [requirements.md](../../requirements.md) (F4.6c, F4.8a, F3.10).

### R4 "Set budget action" (T-UR55)

Decision: on `/plan?tab=budget` an unbudgeted row shows a visible "set budget" button in its budget cell. It opens the budget dialog titled "set budget · <category>" with scope "every month (default)" preselected. A budgeted row keeps the row menu, with the item renamed "edit budget" (was "override"). Scope labels everywhere become "this month only" / "every <month>" / "every month (default)" (was "new default"). When no expense category has any budget, the tab shows a one-line hint that budgets are set per category with "set budget".

Facts: the R4 problem is that a first-time user with no budgets sees only "override", which does not read as "set the default budget". The label change applies to every scope label, not only the menu item.

### R5 "Inline + scope chips" (T-UR56)

Decision: the Plan/year cell keeps inline amount editing and adds a scope chip row under the edited cell: "this month only" / "every <month>" / "every month (default)". The chips are preselected to the cell's current tier (default when the category has no budget). Enter saves with the chosen scope, Escape cancels. The no-JS link keeps opening the dialog.

Facts: today a cell edit writes only a one-off override (F4.8). The operator asked for a choice of scope, with the chip row as the place for it. The no-JS fallback is unchanged.

### R8 "Keep as is" (T-UR59)

Decision: promoted planned rows stay in the Ledger Planned list, marked "promoted", without the promote button. They stay within the default Planned window (today −30 days to today +180 days, or the user's explicit date filter). There is no cleanup job.

Facts: the window is `_PLANNED_LOOKBACK` = 30 days and `_PLANNED_LOOKAHEAD` = 180 days in `web/ledger_data.py:52-53`, applied by `planned_filter` (`web/ledger_data.py:105-124`). The promoted label comes from `_status_cell` in `web/ledger_view.py:468-470`, and the promote button is shown only when the row is not promoted (`web/ledger_view.py:493`). Requirement F3.10 is annotated accordingly.
