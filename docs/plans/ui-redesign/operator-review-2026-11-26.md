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
| R1 | New account button redirects to an empty page | bug | T-UR52 | done |
| R2 | New income category missing from the anchor dropdown until reload | bug | T-UR53 | done |
| R3 | Category picker ignores mouse clicks on desktop | bug (likely regression of WEBKIT bea9ce19 combobox.js) | T-UR54 | done |
| R4 | Plan/budget: make setting the default budget discoverable | design decision (proposal pending) | T-UR55 | decided |
| R5 | Plan/year: cell edit scopes (one-off, every year, default) | design decision (proposal pending) | T-UR56 | decided |
| R6 | Month picker arrows change the picker year only | spec change + fix | T-UR57 | done |
| R7 | Recurring formula always warns non-positive amount | bug | T-UR58 | done |
| R8 | Answer: promoted planned payments in Ledger | question (answer pending) | T-UR59 | decided |
| R9 | Account kind read-only after creation (UI and server) | spec change + fix | T-UR60 | done |
| R10 | No auto-zoom on input focus on touch widths | spec change + fix (inputs >= 16px on touch widths; do NOT disable pinch zoom: a11y) | T-UR61 | done |
| R11 | Mobile overlays squeezed (formula row, override scope) | bug | T-UR62 | done |
| R12 | Mobile ledger filter from/to overlap | bug | T-UR63 | done |
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

## Drill review 2 (2026-11-27)

Second operator drill review, drill run 45987714192 on e2e962b967. The operator's list, verbatim:

- R14 "Plan/budget and year - only display categories that have existing records in Ledger"
- R15 "Edit budget overlay - scope is split to 2 rows"
- R16 "Plan/year - the chips should have only 2 options: `This month only` / `Every <Month-Name>`. No need for the default change here."
- R17 "Plan/year - same chips, I don't like their visual side: 1. No need for the outer box encapsulating them; 2. They are stuck to the left side of the screen, I'd rather see them right beneath the cell I clicked; 3. Seems the chips' colour in light mode is still the dark mode one; 4. Not sure about that, but I'm not entirely convinced that expanding those should move all the rows beneath lower, maybe those could simply hover above those?"
- R18 "In recurring rules - when there are no rules and you click new entry (not the global one, the one displayed under recurring payments) the overlay is opened correctly, but once submitted it goes to an empty page (rising dough headers remain though)"
- R19 "Nice to have - on recurring payment creation fill in the day of the month based on the start date by default (e.g. if user inputs 06-12-2026 the date of the month automatically gets 6), however still allow for manual overwrite of this"
- R20 "Plan/budget - maybe the `set budget` button (for categories without one) would fit better in the status column?"
- R21 "In mobile mode - clicking some fields (e.g. how much can I spend in Today) auto-zooms the page ... how much can I spend in Today works, but there are more places in the app that are affected. Fix all."
- R22 "A few modes in mobile view (e.g. plan/year, plan/forecast) need to be scrolled horizontally ... was there a follow-up work item created for that?" Answer: yes, T-UR64 (documented 2026-11-26); T-UR71 relates.
- R23 "Today in the spent/commited/left bar - currently only commited has a legend icon connecting it to the bar above. Spent and left shall have one as well, do them in the same manner as commited"

### Triage

| R | Item | Class | Task | Status |
|---|---|---|---|---|
| R14 | Budget and year show all categories | spec change + fix | T-UR75 | done |
| R15 | Edit budget scope on one row | fix | T-UR76 | done |
| R16 | Year chips: two options | spec change + fix (supersedes T-UR56 scope set) | T-UR77 | done |
| R17 | Year chips: no box, under cell, overlay, light colours | fix | T-UR77 | done |
| R18 | Recurring empty-state new entry lands on empty page | bug | T-UR78 | done |
| R19 | Day of month defaults from start date | feature | T-UR79 | done |
| R20 | Set budget in the status column | spec change + fix | T-UR80 | done |
| R21 | No auto-zoom on any touch-width input | fix | T-UR81 | done |
| R22 | Wide views scroll horizontally on mobile | follow-up already exists | T-UR64 (relates T-UR71) | deferred |
| R23 | Today bar legend swatches for spent and left | fix | T-UR82 | done |

### Decisions (2026-11-27)

Operator answers, 2026-11-27. Requirement lines: [requirements.md](../../requirements.md) (F4.6c, F4.8, F4.8a, F3.2, §5).

- R14: the current behaviour hides categories without ledger records. Wanted: Plan/budget and Plan/year show ALL categories (live expense categories; archived per ADR-0136 unchanged) whether or not they have ledger records.
- R14 clarified: budgeted categories are rows; every live expense category without a budget (with or without ledger records) sits in the collapsed "N categories without a budget" list on both Plan tabs; on Plan/budget the list shows full rows with "set budget" in the status column.
- R16: two chips only, "this month only" / "every <Month>". "this month only" is ALWAYS preselected; the year cell never changes the default tier (the default stays editable in the budget-tab dialog).
- R17: the chips hover right beneath the clicked cell (overlay above the rows below, nothing shifts), no outer box, kept inside the viewport at the screen edge, light-mode colours correct.
- R20: yes, "set budget" moves into the status column of unbudgeted rows.
- R19: implement; day of month defaults from the start date until the user edits it.
- R23: spent and left get legend swatches like committed.

## Drill review 3 (2026-11-27)

Third operator drill review. The operator's list, verbatim:

- R24 "plan/buget + plan/year - "categories without a budget" - the outer box is ugly, remove it. let the table/list just be a part of the page, no need for adding outer boundaries"
- R25 "plan/buget - also "categories without a budget" - don't display "no budget" next to the "set budget" button"
- R26 "plan/year - the edit toggle chips are floating all around the page in mobile mode, should be fixed to the cell there as well"
- R27 "one more bug - plan/year - when the chips are shown for some cell I'd expect them to disapper when I click elsewhere on the page"

### Triage

| R | Item | Class | Task | Status |
|---|---|---|---|---|
| R24 | Collapsed unbudgeted list has no outer box (budget, year) | fix | T-UR90 | done |
| R25 | Unbudgeted status cell shows only "set budget" | spec change + fix | T-UR91 | done |
| R26 | Year scope chips stay attached to the cell on touch widths | fix | T-UR92 | done (real-phone re-check optional) |
| R27 | A click or tap outside the edited year cell and its chips closes the editor as Escape does | fix + spec change | T-UR93 | done |

## UI accepted (2026-11-27)

The operator accepts the UI state of `ui/sourdough` as of tip `3df85e88`; no further drill review round before the release. Record and consequences: [operator-decisions-2026-11-27.md](operator-decisions-2026-11-27.md) (ADR-0154 Accepted, T-UR65 unblocked).
