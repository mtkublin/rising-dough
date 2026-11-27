# Run 2026-11-26 operator-review-fixes

- Work branch: `ui/sourdough`; base `?`; PR: `?`
- Request: fix the operator drill review items R14-R23 (tasks T-UR75..T-UR82, plus T-UR83 and T-UR78/T-UR79 from the same review), then close the wave bookkeeping.
- Waves: ?; items: 10 merges in this section (see below); agent runs: 35 rows in the table below (the rest are not reconstructed).

## Drill review 3 (2026-11-27)

Source: operator drill review 3 (R24-R27). Tasks marked done in `docs/plans/ui-redesign/tasks.md`: T-UR90, T-UR91, T-UR92, T-UR93. Explore drill 46023778900 on 9503cea2, torn down by run 46031583287.

### Items merged

Merge shas as on `ui/sourdough`.

| item | merge sha | summary |
|---|---|---|
| UNBOX | f732ed4d | collapsed "categories without a budget" list has no outer box; unbudgeted status cell shows only set budget (T-UR90, T-UR91, R24, R25) |
| CHIPMOB | 457f4767 | year scope chips re-place on visual viewport changes and stay attached to the edited cell on touch widths (T-UR92, R26) |
| OUTCLICK | ae8e960f | outside click or tap closes the year cell editor and its chips; value not saved (T-UR93, R27) |

### Agent runs

Verdicts are the role's report status. `?` is an unknown value.

| wave | item | role | model | attempt | wall time | verdict | note |
|---|---|---|---|---|---|---|---|
| ? | UNBOX | implementer | ? | 1 | ? | DONE | |
| ? | UNBOX | visual-auditor | ? | 1 | ? | CLEAN | |
| ? | UNBOX | reviewer | ? | 1 | ? | MERGE | |
| ? | CHIPMOB | implementer | ? | 1 | ? | DONE | |
| ? | CHIPMOB | visual-auditor | ? | 1 | ? | CLEAN | |
| ? | CHIPMOB | reviewer | ? | 1 | ? | MERGE | |
| ? | OUTCLICK | implementer | ? | 1 | ? | DONE | |
| ? | OUTCLICK | visual-auditor | ? | 1 | ? | CLEAN | |
| ? | OUTCLICK | reviewer | ? | 1 | ? | MERGE | |

### Wave tests

| wave | base..head | test-changed | test-e2e | failures (blamed item) |
|---|---|---|---|---|
| ? | ? | ? | CI and e2e green on tip 457f4767 | none on tip |

### Notes

- R26 (CHIPMOB) was not reproduced in Chromium phone emulation on the base; WebKit hangs locally. The fix differs from the base only under pinch zoom. Operator to re-check on a real phone.
- R27 (OUTCLICK: outside click closes the editor) may be the real R26 symptom.
- A touch swipe that starts outside the editor closes it. This is accepted behaviour.
- Affordance observation: the disclosure summary is now plain text with a ▾ marker.

### Load and incidents

- Peak 5-min load: ?.
- Stuck or stopped agents, overruns past 1 h, lock waits: ?.

### Escalations and deferred questions

- ?

## Drill review 2 (2026-11-27)

Source: [operator-review-2026-11-26.md](../plans/ui-redesign/operator-review-2026-11-26.md). Tasks marked done in `docs/plans/ui-redesign/tasks.md`; follow-ups T-UR84..T-UR89 added.

### Items merged

Merge shas as on `ui/sourdough`, first-parent order (newest first).

| item | merge sha | summary |
|---|---|---|
| CIFIX4 | 93f57deb | hero N over keeps counting unbudgeted lines with spend after the collapsed list split (T-UR75; T-UR70 still open); CI was red since PLANCAT 9acc546a on tests/visual/test_overlay_values.py (hero "8 over" vs "6 over", over_count summed only budgeted lines after the split) |
| REFDIFF2 | 098526ca | intended-difference rows for operator reviews R4-R23 (256 reference cases); derived.md F4b line closed (T-UR66, T-UR73). 256 of 264 reference cases signed off as intended, 8 left red: overlays/new-entry--error and overlays/edit-recurring--picking at 1440/1024, pre-existing on e2b3d292 (operator questions q1, q2) |
| ZOOM | 321231ac | no touch-width field below 16px (auth pages included), non-vacuous zoom sweep, year editor and afford fit at 16px (T-UR81, R21) |
| PLANCAT | 9acc546a | Plan/budget and Plan/year: budgeted categories are rows, every live unbudgeted category in the collapsed list, set budget in the status column (T-UR75, T-UR80, R14, R20) |
| YEARCHIP | 7e81a1ba | year cell scope is two chips hovering under the cell, this month preselected (T-UR77, R16, R17) |
| BUDSCOPE | e2b3d292 | budget override scope selector on one row at desktop widths (T-UR76, R15) |
| EMPTYNE | 0267134e | planned and ledger first-run empty-state new entry opens the dialog in place (T-UR83) |
| TODAYLEG | e9ed0d71 | Today spent and left labels carry their bar glyph like committed (T-UR82, R23) |
| RECUR | 95af9e5f | recurring empty-state new entry opens the dialog in place; day of month follows the start date until typed (T-UR78, T-UR79, R18, R19) |
| DOCREV2 | 16010c5a | operator drill review 2 (R14-R23), tasks T-UR75..T-UR82, requirement amendments |
| YEARUX | 7e870377 | year grid cell edit picks its scope inline (T-UR56, F4.8a, R5); T-UR56 superseded by T-UR77 |
| CIFIX3 | bcf445c2 | budget edit link test carries the row tier; picker year-arrow journey waits on the swapped head wrapper |

### Agent runs

Verdicts are the role's report status. Where the brief gave a verdict without naming the role, the role is taken from the step (review -> reviewer, audit -> auditor). `?` is an unknown value.

| wave | item | role | model | attempt | wall time | verdict | note |
|---|---|---|---|---|---|---|---|
| ? | RECUR | implementer | ? | 1 | ? | ? | |
| ? | RECUR | auditor | ? | 1 | ? | CLEAN | |
| ? | RECUR | reviewer | ? | 1 | ? | MERGE | reviewer finding -> EMPTYNE |
| ? | TODAYLEG | implementer | ? | 1 | ? | ? | |
| ? | TODAYLEG | reviewer | ? | 1 | ? | RETURN | glyph constants |
| ? | TODAYLEG | implementer | haiku | 2 | ? | ? | fix round |
| ? | TODAYLEG | reviewer | ? | 2 | ? | MERGE | |
| ? | PLANCAT | implementer | ? | 1 | ? | ? | |
| ? | PLANCAT | reviewer | ? | 1 | ? | RETURN | usage split inverted |
| ? | PLANCAT | implementer | ? | 2 | ? | ? | rework after operator clarified R14 mid-run: all unbudgeted in the collapsed list on both tabs, set budget in the status column |
| ? | PLANCAT | auditor | ? | 1 | ? | FINDINGS | archived in year list, 375 card layout |
| ? | PLANCAT | implementer | ? | 3 | ? | ? | fix |
| ? | PLANCAT | auditor | ? | 2 | ? | FINDINGS | re-audit: past-year archived links 404 |
| ? | PLANCAT | implementer | ? | 4 | ? | ? | fix |
| ? | PLANCAT | auditor | ? | 3 | ? | CLEAN | |
| ? | PLANCAT | reviewer | ? | 1 | ? | MERGE | 4 implementer rounds in total |
| ? | YEARCHIP | implementer | ? | 1 | ? | ? | |
| ? | YEARCHIP | auditor | ? | 1 | ? | FINDINGS | no vertical clamp |
| ? | YEARCHIP | implementer | ? | 2 | ? | ? | fix |
| ? | YEARCHIP | auditor | ? | 2 | ? | FINDINGS | re-audit: 4px overlap |
| ? | YEARCHIP | implementer | ? | 3 | ? | stopped | fix; agent stopped without commit, handed over to a new agent |
| ? | YEARCHIP | auditor | ? | 3 | ? | CLEAN | re-check |
| ? | YEARCHIP | reviewer | ? | 1 | ? | MERGE | |
| ? | BUDSCOPE | implementer | ? | 1 | ? | ? | |
| ? | BUDSCOPE | auditor | ? | 1 | ? | CLEAN | |
| ? | BUDSCOPE | reviewer | ? | 1 | ? | MERGE | |
| ? | ZOOM | implementer | ? | 1 | ? | ? | |
| ? | ZOOM | reviewer | ? | 1 | ? | RETURN | selectors moved into evaluate (guard dodge); vacuous sweep |
| ? | ZOOM | auditor | ? | 1 | ? | FINDINGS | auth pages at 14px |
| ? | ZOOM | implementer | ? | 2 | ~61 min | ? | fix round; 4 CI e2e runs; overran the 60 min budget |
| ? | ZOOM | auditor | ? | 2 | ? | CLEAN | re-audit |
| ? | ZOOM | reviewer | ? | 2 | ? | MERGE | |
| ? | EMPTYNE | implementer | ? | 1 | ? | ? | from RECUR reviewer finding |
| ? | EMPTYNE | auditor | ? | 1 | ? | CLEAN | |
| ? | EMPTYNE | reviewer | ? | 1 | ? | MERGE | |
| ? | CIFIX4 | implementer | ? | 1 | ? | ? | CI red since PLANCAT 9acc546a on tests/visual/test_overlay_values.py: hero "8 over" vs "6 over" |
| ? | CIFIX4 | reviewer | ? | 1 | ? | MERGE | |
| ? | REFDIFF2 | implementer | ? | 1 | ? | ? | 256 of 264 reference cases signed off as intended; 8 left red (pre-existing on e2b3d292) |
| ? | REFDIFF2 | reviewer | ? | 1 | ? | MERGE | |

Note: the run table lists the runs the brief records. Runs for YEARUX and CIFIX3 are not in the brief and are not reconstructed.

### Wave tests

| wave | base..head | test-changed | test-e2e | failures (blamed item) |
|---|---|---|---|---|
| ? | ? | ? | ZOOM: 4 CI e2e runs during the fix round | ? |

### Load and incidents

- Peak 5-min load: ? (not recorded).
- GitHub API rate limit exhausted 13:06-13:27 UTC by parallel `gh run watch` polling. Cause: agents polled in parallel. Fix: agents told to use one watch with `--interval 60`.
- Main checkout found detached at the same sha (an agent's checkout); the orchestrator reattached it before the RECUR merge.
- Several agent final reports arrived empty ("placeholder") or interim. The verdicts above were read from the worktree and the audit record instead.
- Stuck or stopped agents: YEARCHIP fix agent stopped without commit; work handed over to a new agent.
- Overruns past 1 h: none recorded; ZOOM fix round ran ~61 min against a 60 min budget.
- Lock waits: ?.

### Escalations and deferred questions

- PLANCAT: operator clarified R14 mid-run (all unbudgeted categories in the collapsed list on both tabs, set budget in the status column); rework followed.
- TODAYLEG: reviewer RETURN -> fix round by a haiku implementer -> MERGE.
- Deferred operator list (no earlier list in this run log):
  - T-UR22 drill workflow patch (`q-t-ur22-drill-workflow.md`)
  - T-UR66 visual reference trigger patch
  - ci.yml edits (`q2-ci-checkout.md`, `q-ci-tailwind-removal.md`)
  - SETUP_TOKEN_HASH secret
  - T-UR40 ruleset
  - PR #54 ready
  - ADR-0154 clash note for PR #59
  - CSP parked branch
  - q1: sign off overlays/new-entry--error (app leaves Takeaway unchecked beside "Pick a category") as intended?
  - q2: overlays/edit-recurring--picking category-list diff: bug or intended?
  - q3: T-UR70 hero "N over" counts unbudgeted categories with spend: keep?
