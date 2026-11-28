# ADR-0154: Accepted UI Screenshots Replace the Handoff References

- **Status**: Accepted (2026-11-27: operator accepted the UI on `ui/sourdough` tip `3df85e88`, [operator-decisions-2026-11-27.md](../plans/ui-redesign/operator-decisions-2026-11-27.md); implementation pending, T-UR65)
- **Date**: 2026-11-26
- **Supersedes (in part, on acceptance)**: [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md) §1 (CI-rendered handoff references), the data overlay and the cluster-cap comparison against the handoff
- **Relates to**: [ADR-0027](0027-frontend-toolchain-hardening.md) (visual suite, baselines), [ADR-0106](0106-ui-behaviour-test-harness.md), [ADR-0121](0121-drill-gate-skip-for-non-deploy-prs.md) (gate skip pattern)

## Context

ADR-0147 renders the designer's handoff in CI and compares every surface (1272 tests, six shards, advisory). The operator decision of 2026-11-26 ("Intended differences and the gate", `operator-decisions-2026-11-26.md`) accepts differences between the app and the handoff (data the app cannot reproduce, intended deviations) and carries them as `xfail(strict=True)` rows plus an overlay. Two operator asks followed:

1. Once the drill UI is green-lit, the reference images for the visual tests should be the approved UI state, not the handoff.
2. Running every visual pipeline on every PR is excessive.

The handoff stays the design source for new work; it stops being the pixel reference for regression once the UI is accepted.

## Decision

1. **Trigger.** On operator acceptance of the UI after the explore drill (recorded in `operator-decisions-*.md`), the app's own screenshots become the baselines. Until then ADR-0147 stands unchanged.
2. **How baselines are made.** Only by `visual.yml` `workflow_dispatch` with `update_baselines=true`, dispatched by the operator, in the pinned Playwright container (Linux-only, ADR-0027). The workflow uploads the `visual-baselines` artifact and never commits (unchanged); an agent downloads the artifact and commits it under `tests/visual/__snapshots__/` in a normal PR. No local-host baselines.
3. **One per-PR visual job.** The existing `visual` job (path-filtered by `changes`, as today) is the only visual job on `pull_request`. `visual-gate` stays the required check, unchanged.
4. **Retire the handoff comparison from the regression path.** Removed on acceptance: the `reference` job (six-shard matrix) from `visual.yml`, the handoff overlay rows, the "Intended differences" `xfail` table in `derived.md` and in `tests/visual/test_reference.py`. Decision: remove the per-PR run and the xfails; **keep the render script and `visual_in_container.sh reference` as a manual tool** (designer comparisons on `workflow_dispatch` only), because a new designer delivery still needs a side-by-side. It has no gate role and no schedule after T-UR65.
5. **Interim.** Before acceptance, the `reference` job moves off the per-PR path (T-UR66): `schedule` and `workflow_dispatch` only. No app or test change.
6. **Later required comparison.** The accepted-baseline comparison is the `visual` job itself; no second required check is added.

## Cost

Per frontend PR: `changes` + `visual` + `visual-gate` (one container job, about 30 min budget) instead of that plus six 45-minute `reference` shards. Non-frontend PRs: `changes` only, gate auto-satisfied. The weekly schedule and manual dispatch remain.

## Consequences

- Regression becomes "did this PR change an accepted pixel", with no overlay workarounds or xfails.
- A deliberate visual change needs an operator-dispatched baseline update and a baseline commit in the same PR; reviewers see the image diff.
- Baselines are Linux-container only; the pin test (`test_visual_image_pin.py`) still applies.
- Operator patches to `.github/workflows/visual.yml` are needed (agents lack the workflow scope): [q-visual-reference-trigger.md](../plans/ui-redesign/q-visual-reference-trigger.md).

## Amendment 2026-11-28 (T-UR65): the baseline root is not old frontend

The accepted-UI baselines committed under `tests/visual/__snapshots__/` (decision 2) are accepted-UI references, not old frontend. The old 24 snapshots (`<page>.<width>.png`, the ADR-0107 §8 removal ledger rows) are deleted and stay listed as `deleted`. The new files are named `<case>.<width>.<theme>.png`. The ADR-0107 §8 removal guard (`tests/architecture/test_old_frontend_removed.py`) therefore treats `tests/visual/__snapshots__/` as an allowed new root: files under it need no ledger row, and the `deleted` rows still fail if their old file reappears. The root stays in `OLD_ROOTS` so the guard keeps scanning it.
