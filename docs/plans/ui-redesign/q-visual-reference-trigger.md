# Operator patch: visual.yml reference job off the per-PR path (T-UR66, T-UR65)

Applied 2026-11-28 by WFPATCH (part 2: the `reference` job removed from visual.yml; part 1 superseded; test side: handoff comparison tests, `just test-visual` and the `reference` mode of visual_in_container.sh removed, mapping moved to tests/visual/reference_map.py).

Agents cannot push `.github/workflows/*` (no workflow scope), so you apply these edits. Context: [ADR-0154](../../adr/0154-accepted-ui-screenshots-replace-the-handoff-references.md).

## Part 1 (T-UR66, apply now)

In `.github/workflows/visual.yml`, job `reference`, change the `if:` line only (keep `needs: changes`, `continue-on-error`, the matrix and all steps):

```diff
   reference:
     name: handoff reference comparison ${{ matrix.shard }} (advisory)
     needs: changes
-    if: needs.changes.outputs.relevant == 'true'
+    if: needs.changes.outputs.relevant == 'true' && github.event_name != 'pull_request'
```

Also update the comment above the job: append "Runs on schedule and workflow_dispatch only (ADR-0154 §5)."

`visual-gate` is untouched (it never depended on `reference`).

### Apply

Edit on a branch with a token that has the `workflow` scope (or in the GitHub web editor), open a PR to the work branch, merge.

### Verify

Open or update a PR touching a template or CSS file. The checks list shows only `classify changed files`, `visual suite (pinned Playwright container)` and `visual-gate`; no `handoff reference comparison ...` entries. A manual run (Actions > Visual > Run workflow) and the Monday schedule still run all six `reference` shards.

## Part 2 (T-UR65, apply after the operator accepts the UI and baselines are committed)

Order: (1) dispatch `visual.yml` with `update_baselines=true`; (2) an agent commits the `visual-baselines` artifact; (3) apply this patch with the test cleanup.

Remove the whole `reference` job from `.github/workflows/visual.yml` (from the ADR-0147 comment block above `reference:` through its last step `Upload actual images and diffs of failing comparisons`):

```diff
-  # ADR-0147 section 1: the handoff references are rendered here ...
-  reference:
-    name: handoff reference comparison ${{ matrix.shard }} (advisory)
-    ...
-          path: visual-actual/
-          if-no-files-found: ignore
```

Update the header comment to say baselines are the accepted-UI screenshots (ADR-0154). If you want the manual designer comparison to stay, keep the `reference` mode of `scripts/ci/visual_in_container.sh` (a repo script, not a workflow) and run it locally or through a dedicated `workflow_dispatch`-only workflow later.

Verify: a frontend PR shows `visual` + `visual-gate`; `visual` fails on an unintended pixel change against the committed baselines.
