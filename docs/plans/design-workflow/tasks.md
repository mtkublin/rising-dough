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
- Done 2026-11-25: https://claude.ai/artifact/Q9n5eDZg4KWdFKCb5WAYWy.

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

### T-DW10 [S] Guard: UI-facing change needs a design reference → T-DW09
- ADR-0151 §6.
- Goal: a check (in `check_item.py` for orchestrated items and a PR CI step) that fails a change under `src/budget_planner/web/templates/`, `src/budget_planner/web/static/` when the task, brief or PR names no `docs/design/<name>/` page or `docs/design/specs/` file.
- Acceptance: unit tests with exact outputs; the redesign migration items pass by citing `docs/design/rising-dough-frontend/`.

### T-DW07 [S] Prove artboard reference rendering on the first real canvas → T-DW05, T-DW06
- ADR-0151 §4 "Artboard references".
- Goal: render a canvas artboard's `.dc.html` locally to PNG at its width and theme, or record that it cannot be done and keep the operator-export fallback.
- Acceptance: the method (or the fallback) is written into `.claude/agents/handoff-builder.md` and the template; one package passes `--parity` with references made that way.

### T-DW08 [S] Parity cluster cap → T-DW04 (blocked on the `ui/sourdough` merge)
- ADR-0151 §3, ADR-0147 §2.
- Goal: `--parity` uses `tests/visual/handoff.compare` / `passes` with `MAX_DIFF_CLUSTER_PX` once they are on `main` (they are on `ui/sourdough` today); until then it uses `diff_ratio` and the 0.1 % ratio only.
- Acceptance: `check_handoff.py` imports the cluster check; its test covers a small cluster that stays under the ratio and fails the cap.
