# Design Workflow From the Repo — Tasks

> Flat index. Method: [implementation_plan.md](implementation_plan.md). Decision: [ADR-0151](../../adr/0151-designer-skill-handoff-builder-and-package-template.md).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-DWxx` depends on upstream task.

---

### ✅ T-DW01 [S] Decision record (docs only)
- Docs-first step: this entry; ADR-0151; ADR-0107 and ADR-0129 amendments 2026-11-25; `docs/requirements.md` §13.
- Acceptance: ADR-0151 and its index row exist; ADR-0107 and ADR-0129 carry dated amendments naming it; requirements §13 lists the outputs; `docs/CHANGELOG.md` has a line.

### ✅ T-DW02 [S] Combined design system in the repo → T-DW01
- ADR-0151 §1.
- Goal: `docs/design/system/project/` (README brand book, generated `tokens.json`, index); `scripts/design_system.py` + `just design-system` generate `tokens.json` from the base `static/css/tokens.css`; `--check` fails when the committed file is stale.
- Acceptance: unit tests with exact token output (`tests/unit/deploy/test_design_system.py`); the system published to claude.ai as a new Design System artifact and its URL recorded in `docs/design/system/README.md`; no existing remote system changed.
- Done 2026-11-25: https://claude.ai/artifact/Q9n5eDZg4KWdFKCb5WAYWy. Components added the same day from the base package (`components/bundle.css`, 11 generated previews + READMEs; `--check` covers them; test: previews carry no colour literal).

### ✅ T-DW03 [S] Handoff package template → T-DW01
- ADR-0151 §3.
- Goal: `docs/design/handoff-template.md` (manifest, layout, one markup, tokens only, self-contained, wired, 1-to-1, README sections) and `docs/design/specs/README.md`, `docs/design/requests/README.md` (spec and change-request formats).
- Acceptance: every rule in the template names the `check_handoff.py` check that enforces it, or says "reviewer".

### ✅ T-DW04 [S] `scripts/ci/check_handoff.py`: executable Definition of Done for a package → T-DW03
- ADR-0151 §4.
- Goal: static checks, `--render` (load, console, requests, overflow, theme, wiring), `--parity <refs>`, `--write-manifest`; `just check-handoff <dir> [flags]`.
- Acceptance: unit tests on the pure checks with exact outputs, plus one render test on a fixture package (skipped when Chromium is missing) (`tests/unit/deploy/test_check_handoff.py`).

### ✅ T-DW05 [S] `/designer` skill → T-DW02, T-DW03
- ADR-0151 §2.
- Acceptance: `.claude/skills/designer/SKILL.md` with the flow (current UI, canvas with paired light/dark artboards, comment loop, spec, change requests, hand-off to the builder); links CLAUDE.md and ADR-0151 instead of restating them.

### ✅ T-DW06 [S] `handoff-builder` agent → T-DW03, T-DW04
- ADR-0151 §4.
- Acceptance: `.claude/agents/handoff-builder.md` with valid frontmatter (`name`, `description`, `tools`, `model`), the build steps, `just check-handoff` as its DoD and the ADR-0150 §4 report block.

### ✅ T-DW09 [S] Design gate for every UI-facing change (docs only) → T-DW01
- Operator decision 2026-11-25. ADR-0151 §6; requirements §13.2; CLAUDE.md "Design gate"; `implementer` and `reviewer` rules.
- Acceptance: CLAUDE.md states the gate and the design reference; the implementer stops and the reviewer returns a UI-facing change without one.

### ✅ T-DW10 [S] Guard: UI-facing change needs a design reference → T-DW09 (folded into T-DW11)
- Re-scoped 2026-11-26 by ADR-0152 §2: a design reference is no longer required for every UI change, so there is no reference guard. Its enforcement role moved to G33 (T-DW11) and the `ui-reviewer` (T-DW12), which `ESCALATE` new design that skipped `/designer`.

### ✅ T-DW11 [S] `scripts/ci/check_ui.py` and guard G33 → T-DW02
- ADR-0152 §3.
- Done 2026-11-26: `just check-ui [base]` checks added lines of templates and static CSS/JS/SVG (colours, lengths, tokens; hints: new template, new component, new property; layers line). Calibrated on the `ui/sourdough` diff: one real finding (`--color-muted` undefined, from the base package), no false positive after exempting `0` lengths, the category palette and `img/`. G33 `tests/architecture/test_ui_review.py` runs it on the branch diff and requires `## UI review` with `VERDICT: PASS` in the audit record. Tests: `tests/unit/deploy/test_check_ui.py`.

### ✅ T-DW12 [S] `ui-reviewer` agent and `/ui-review` skill → T-DW11
- ADR-0152 §1, §3-§5.
- Done 2026-11-26: `.claude/agents/ui-reviewer.md` (opus; layers, rubric, verdicts, record section), `.claude/skills/ui-review/SKILL.md`; `orchestrator-mode` Step 3 dispatches it after the `visual-auditor`; CLAUDE.md "Design gate", `implementer`, `reviewer` and `/designer` rules follow ADR-0152 §2.
- Open: first real run on a UI change after `ui/sourdough` lands (proves state reachability on the demo DB).

### T-DW07 [S] Prove artboard reference rendering on the first real canvas → T-DW05, T-DW06
- ADR-0151 §4 "Artboard references".
- Goal: render a canvas artboard's `.dc.html` locally to PNG at its width and theme, or record that it cannot be done and keep the operator-export fallback.
- Acceptance: the method (or the fallback) is written into `.claude/agents/handoff-builder.md` and the template; one package passes `--parity` with references made that way.

### T-DW08 [S] Parity cluster cap → T-DW04 (blocked on the `ui/sourdough` merge)
- ADR-0151 §3, ADR-0147 §2.
- Goal: `--parity` uses `tests/visual/handoff.compare` / `passes` with `MAX_DIFF_CLUSTER_PX` once they are on `main` (they are on `ui/sourdough` today); until then it uses `diff_ratio` and the 0.1 % ratio only.
- Acceptance: `check_handoff.py` imports the cluster check; its test covers a small cluster that stays under the ratio and fails the cap.
