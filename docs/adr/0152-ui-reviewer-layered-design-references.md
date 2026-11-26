# ADR-0152: A UI Reviewer That Checks Every UI Change Against Layered Design References

- **Status**: Accepted
- **Date**: 2026-11-26
- **Amends**: [ADR-0151](0151-designer-skill-handoff-builder-and-package-template.md) §6 (the design gate: only new design goes through the designer; every UI change goes through the UI reviewer)
- **Related**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md), [ADR-0150](0150-orchestrator-role-agents-executable-dod-and-wave-testing.md)
- **Tasks**: T-DW10 (re-scoped), T-DW11, T-DW12 (`docs/plans/design-workflow/tasks.md`)

## Context

ADR-0151 §6 made every UI-facing change, however small, wait for a designer round and an agreed design reference; without one the implementer stopped and the reviewer returned. Two problems:

- A one-line fix (a label, a missing error state, a spacing bug) cost a canvas, a comment loop and a package. Small changes either stall or the rule gets ignored.
- Nobody checked the result. The code `reviewer` reads diffs, the `visual-auditor` looks for overflow and console errors, and parity (ADR-0147) compares against a package page only when one exists. Whether a change looks and works like the rest of the app was nobody's job.

The operator wants a UI reviewer that checks every UI change against what is available, in order: the design system (always, most important), the established app design (once the redesign has landed), and the designer's handoff (when there is one, deviations allowed when documented and reasoned), plus aesthetics and UX in every case.

## Decision

### 1. Layered design references

Every UI-facing change (ADR-0151 §6 definition) is reviewed against the layers that exist for it:

| Layer | Applies | Weight |
|---|---|---|
| **Design system** `docs/design/system/` (tokens, components, both themes) | always | strictest: a violation is `RETURN` |
| **Established base UI**: the shipped app's chrome, components and patterns | once the base UI is on `main`: `src/budget_planner/web/static/rd/css/main.css` exists at the merge base (the `ui/sourdough` merge) | a break with sibling screens is `RETURN` unless the change documents why |
| **Designer handoff**: a package page or spec named by the change | when the change names one | parity; a documented deviation is checked for kept intent, otherwise `ESCALATE` |
| **Aesthetics and UX** | always | a fixed rubric (§4); only defects with evidence block |

A missing handoff is not a failure. The reviewer reviews against the layers that exist.

A change that follows a handoff but departs from it lists each departure in its PR description under `## Design deviations`, numbered, each with a reason (the package's own `[[deviation]]` rows cover the package against the canvas, not the app against the package).

### 2. The design gate, amended (ADR-0151 §6)

- **New design goes through `/designer` first:** a new screen, flow, dialog or component, a new pattern, a new token, or a visible redesign of an existing surface. The designer's spec or package is then the handoff layer.
- **Everything else** (a fix, a copy tweak, a new field in an existing form, a missing state built from existing components) needs no designer round. It goes straight to the UI reviewer.
- **Every UI-facing change goes through the UI reviewer** before merge. If the reviewer finds new design that skipped the designer, its verdict is `ESCALATE` to the operator, who decides between `/designer` and accepting it.
- The implementer no longer stops for a missing reference. It names one when it has one, and otherwise builds from existing components and tokens only.

### 3. Two parts: a script for the mechanical half, an agent for judgement

**`scripts/ci/check_ui.py` (`just check-ui [base]`)** checks the lines a branch adds under `src/budget_planner/web/templates/` and `src/budget_planner/web/static/` against its merge base:

- **FAIL `colours`**: a colour literal outside a `tokens.css` (reuses `check_handoff.colour_literals`).
- **FAIL `lengths`**: a literal length (`px`, `rem`, `em`) in `padding`, `margin`, `gap`, `inset`, `border-radius`, `font-size`, `line-height` or `letter-spacing` instead of a token. The base package has none.
- **FAIL `tokens`**: a `var(--x)` that nothing defines, or a new design-system token (`--color-`, `--space-`, `--radius-`, `--font-`, `--shadow-`, `--size-` families) defined outside the system.
- **Hints** (no failure, for the reviewer and the `ESCALATE` decision): a new template file, a new `.rd-<block>` selector the system's `bundle.css` lacks, a new component-scoped custom property, an `rd-*` class nothing defines.
- **Layers**: which of §1 apply (base UI on or off; handoff references from `Design-Ref:` commit trailers and from `docs/design/` paths the branch touches).

Guard **G33** (`tests/architecture/test_ui_review.py`) runs the script's checks on the branch diff in the suite and in PR CI. It also requires the frontend audit record (G31) of a UI-facing change to carry a `## UI review` section with `VERDICT: PASS`.

**`ui-reviewer` agent** (`.claude/agents/ui-reviewer.md`, read-only apart from its record section): runs `just check-ui`, renders the touched routes with the `frontend-visual-audit` skill at 1440, 1024 and 375 in light and dark, reaches the states the change touches (empty, error, loading, long content, menu open) on a scratch copy of the demo DB, compares with the layers that apply, and writes the `## UI review` section. It runs in its own context, separate from the session that made the change, and gets screenshots, the diff and the references, not the implementer's summary.

Verdicts:

- **PASS**: no blocking finding. Suggestions are listed and do not block.
- **RETURN**: a design-system violation, a break with the base UI without a reason, an undocumented deviation from the handoff, or a UX defect it can point at.
- **ESCALATE**: a question only the operator or the designer can answer: new design that skipped the designer, a documented deviation that changes the design's intent, or a "this should be redesigned" judgement.

The reviewer never approves a deviation from a handoff on its own judgement of the reasoning: it checks that the reason exists and that the design's intent survives; changed intent is `ESCALATE`.

### 4. Aesthetics and UX rubric

The agent judges against a fixed list, so findings are comparable and the noise stays low:

- **Visual:** one focal point and one primary action per surface; alignment and spacing rhythm; density consistent with sibling screens; the type scale; both themes balanced (nothing vanishes or glares in dark).
- **UX:** affordance; feedback for every action (pending, success, error); error recovery; empty states that say what to do next; destructive actions confirmed or undoable; keyboard reach and focus order; touch targets and thumb reach at 375; clear, consistent copy.
- Only a finding with evidence (route, viewport, theme, screenshot, file:line) can `RETURN`. Taste is a suggestion.

### 5. Where it runs

- **Orchestrated runs** (ADR-0150): for a template, CSS or HTMX item, the orchestrator dispatches the `ui-reviewer` after the `visual-auditor`'s record exists and before merging; only `PASS` merges a UI item. `ESCALATE` goes into the operator question batch; the operator's answer, quoted in the PR, closes it on the re-review.
- **Single sessions**: the `/ui-review` skill dispatches the agent for the current branch.
- The `ui-reviewer` is not one of the hook-guarded role agents (ADR-0150 amendment 2026-11-25); its own definition limits it to its record section.

## Consequences

- Small UI fixes no longer wait for a canvas; new design still does, and skipping it is caught as `ESCALATE` instead of being blocked up front.
- The mechanical half of design-system compliance is a guard, so it runs on every PR for free; the agent spends its time on what needs eyes.
- The "established base UI" layer switches on by itself when `ui/sourdough` lands on `main`; until then the base package is reached through the handoff layer.
- Cost: an extra agent per UI item, with screenshots in two themes at three widths for the touched routes only.
- Agent judgement is noisy. The rubric, the evidence rule and `ESCALATE` for taste questions keep it from blocking on opinion.

## Alternatives considered

- **Keep ADR-0151 §6 as written (every UI change needs a reference first)**: rejected by the operator; it blocks small fixes and still leaves nobody checking the result.
- **One agent judges all layers, no script**: rejected; most design-system rules are exact and belong in a guard, where they cost nothing and cannot be talked around.
- **Fold the UI review into the code `reviewer`**: rejected; it needs screenshots, a running app and a separate context from the code review, and the code reviewer's runtime budget is 30 minutes.
