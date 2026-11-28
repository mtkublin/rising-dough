# Operator decisions, 2026-11-27 (ui/sourdough)

Binding for the rest of the run.

## UI accepted

- **The operator accepts the UI state of the `ui/sourdough` migration as of tip `3df85e88`** (drill reviews R1-R27 merged; CI and e2e green on `ae8e960f`; last explore drill 46023778900). Operator words: "As of the current state - I approve the UI state of ui/sourdough migration."
- This is the acceptance that [ADR-0154](../../adr/0154-accepted-ui-screenshots-replace-the-handoff-references.md) §1 waits for: ADR-0154 is Accepted from today, and [T-UR65](tasks.md) is unblocked on the acceptance side (it still needs the operator's baseline dispatch and workflow patch).
- No more drill review round is planned before the release. Later visual changes need a baseline update (ADR-0154 §2).

## What the acceptance settles

- **Reference reds** (open question from drill review 2): `overlays/new-entry--error` and `overlays/edit-recurring--picking` at 1440 / 1024, and the small corner clusters on `category-picker` 1024 and `reconcile` 375 light, are accepted as they render now. They leave with the handoff comparison in T-UR65; no designer question, no fix. T-UR50's remaining scope is superseded by T-UR65.
- **R26** (year chips on a real phone): the acceptance covers the current behaviour; the real-phone re-check is optional. A problem found later is a normal bug.
- **Not settled by a UI acceptance** (behaviour or tooling): T-UR70, the parked CSP branch (T-UR16), planned-save flash miss, case-sensitive duplicate category names, follow-ups T-UR68, T-UR69, T-UR71, T-UR74, T-UR84..T-UR89. Decided in "Pre-release scope" below. D6-B stays as decided on 2026-11-26 (keep ADR-0089).

## Pre-release scope (operator, 2026-11-27)

"Let's do all we can before the release." Every open item below lands before T-UR17 unless it needs an operator step; operator questions are collected until the work is done.

- **CSP (T-UR16 hardening)**: one timeboxed attempt (under 1 h) on `wi/ui/sourdough/CSP` to find the WebKit `style-src-attr` source and ship `style-src 'self'`. If not solved, the release keeps `'unsafe-inline'` and the hardening becomes a post-release follow-up.
- **T-UR70**: hero "N over" and Total count **budgeted rows only**; unbudgeted spend shows only in the collapsed "N categories without a budget" list. Requirement F4.6c first.
- **Duplicate category names**: create and rename reject a name equal, **ignoring case**, to another live category of the same direction (422 on name). No data migration (prod has no such pair).
- **T-UR68**: the category picker's no-match state offers `create "<typed>"`; it creates the category (direction from the entry tab), selects it, and the new-entry dialog stays open with its typed values.
