# ADR-0099: Release and Environment Policy

- **Status**: Accepted; required merge checks amended by [ADR-0121](0121-path-filtered-workflows-are-not-required-checks.md) (path-filtered Terraform checks are not required)
- **Date**: 2026-11-07
- **Relates to**: ADR-0035, ADR-0037, ADR-0094, ADR-0096, ADR-0097, ADR-0098; forward-references ADR-0100 (CI credentials, written by T-D92)

## Context

v3 has two environments, `prod` and `drill` (disposable). Until now nothing stated who may build, apply or deploy to prod, and the existing `deploy.yml` chains `build -> drill -> prod` through `workflow_run`. During bring-up, applies ran from the operator laptop with an admin Scaleway key in `terraform/.env`, and a plan leaked secrets (ADR-0098). Prod holds the only canonical user data, so the release path must be single, auditable and enforced technically, not by convention.

## Decision

1. **Prod releases only via GitHub Actions from `main`.** Nothing builds, applies, deploys or pushes images for prod from anywhere else: not laptops, not other branches, not ad-hoc dispatch on non-`main` refs.
2. **Main pipeline** (dependency tree): push to `main` -> `ci` -> `build` (only if ci is green; publishes the immutable `sha-<short>` image and its cosign signature) -> `terraform apply prod` (GitHub environment `prod`, required reviewer approval; image tag taken from the build output) -> `deploy prod` (SSH image swap over the tailnet, environment `prod`, ADR-0037, ADR-0094) -> smoke `/ready`. Implemented by a new orchestrating `release.yml` that calls reusable (`workflow_call`) ci / build / terraform / deploy workflows (T-D89). There is no drill stage on `main`: the drill is validated pre-merge (item 3).
3. **Drill deploys** (T-D90). One reusable drill pipeline: build -> terraform apply drill (server and tailnet key replaced) -> deploy -> smoke. Triggers:
   - push to any branch matching `*-deploy`, and `workflow_dispatch` on any branch (input `ttl_minutes`, default 60). The drill stays up for the TTL; a scheduled sweeper (every 15 min) destroys expired drills; a manual `drill-destroy` dispatch tears down early.
   - `pull_request` to `main`: pre-merge gate. Ephemeral drill, torn down at the end of that pipeline (success or failure). Required check before merge.
   - There is a single drill environment, so all drill workflows share one concurrency group (`drill`), queued not cancelled. `restore-drill.yml` joins it.
4. **Exceptions** (the only non-GitHub actions allowed):
   a. One-time initial prod bring-up from the operator laptop on 2026-11-07 (terraform apply of prod with image `sha-075f986`, plan reviewed by the user). After it, item 1 applies without exception.
   b. The bootstrap stack (`terraform/bootstrap`, ADR-0096) stays local-only: it creates the state buckets and the CI credentials CI cannot create for itself.
   c. Break-glass for a GitHub outage or stuck state lock: an org-admin Scaleway key kept only in the operator's password manager (never in `terraform/.env`); each use is logged in `docs/CHANGELOG.md` with the reason. Runbook: [break-glass.md](../plans/v3/runbooks/break-glass.md) (written by T-D92).
   d. One-time copy of the local prod DB (`data/budget.sqlite`) to the prod instance once prod is up, before real use: consistent snapshot via `sqlite3 .backup`, transferred over the tailnet, app and Litestream stopped, migrations run on app start, Litestream starts a new generation. Requires explicit in-session user go at execution time (the CLAUDE.md prod-DB rule still applies). Runbook and script: [prod-db-seed.md](../plans/v3/runbooks/prod-db-seed.md) (T-D93).
5. **Enforcement is by credentials, not convention.** After T-D92 the only prod-write credentials live in the GitHub `prod` environment secrets (least-privilege CI IAM application per environment, created by the bootstrap stack, ADR-0100). The leaked admin key is rotated and `terraform/.env` keeps no prod-write key. Manual GitHub settings (checklist, T-D92):
   - environment `prod`: required reviewer, deployment branch policy `main` only;
   - environment `drill`: branches `*-deploy`, `main` and PR refs;
   - branch protection on `main` requiring `ci` and the pre-merge drill check.
6. **CI policy unchanged** (ADR-0097). The temporary `v3` push trigger in `build.yml` (T-D76) is removed by T-D89.

## Consequences

- One auditable path to prod; a laptop or feature branch cannot touch it because it lacks the credentials and the environment branch policy rejects it.
- Every PR to `main` pays one drill cycle (apply, deploy, smoke, destroy) and serialises behind other drill runs.
- `deploy.yml`'s `workflow_run` chain (drill then prod) and the docs describing it are superseded by T-D89 and T-D90; until they land, existing workflows and runbooks describe the old flow.
- Break-glass and the prod DB seed are explicit, logged exceptions rather than silent habits.
- The 1 h default TTL bounds drill cost and the lifetime of drill secrets and break-glass access.

## Alternatives considered

- **Branch suffix `*-deploy` alone**: forces renaming branches to get a drill. Rejected as the only trigger; kept for push-to-deploy.
- **`workflow_dispatch` alone**: loses push-to-deploy. Rejected as the only trigger; kept for any-branch drills.
- **PR label to start a drill**: ties drills to PRs and needs a PR first. Considered and rejected.
- **Drill stage on `main` before prod** (the old `workflow_run` chain): duplicates the pre-merge gate and slows every release. Rejected.
- **Convention only** (documented rule, admin key on laptop): a leaked or stale key already proved this fragile. Rejected in favour of credential scoping.

## Amendment 2026-11-07 (T-D90)

- The drill pipeline smoke-tests instead of calling `deploy.yml`: every drill apply replaces the server, and the fresh boot's cloud-init already runs `app_image_tag` (the freshly built tag), so the SSH swap would be a no-op. The smoke job waits for the public `/ready` (budget 10 min; fresh boot ~3.5 min). `deploy.yml` still accepts `env: drill` for ad-hoc use.
- TTL is stored as the Scaleway server tag `expires-at=<RFC3339 UTC>` (Terraform var `drill_expires_at`, drill-only) so the sweeper needs no state access.
- Destroy runs pass the placeholder `image_tag: sha-0000000`; `app_image_tag` only feeds user-data, which a destroy plan never creates.

## Amendment 2026-11-07 (T-D96, T-D97, ADR-0101)

- Drill apply is human-gated: environment `drill` has required reviewers; destroy/sweeper/smoke use the ungated `drill-teardown`, the PR plan leg uses `drill-plan`.
- The drill is tailnet-only (no public DNS, no public 80/443). The smoke job joins the tailnet and probes `https://budget-planner-drill.<tailnet>.ts.net/ready`; the "public `/ready`" wording above is superseded for the drill. See [ADR-0101](0101-drill-environment-is-tailnet-only.md).

## Amendment 2026-11-07 (T-D98): drill is manual-only; the PR gate is a commit status

Supersedes the `*-deploy` push and `pull_request` triggers of decision 3 (and the matching line in decision 5). `drill.yml` is triggered by `workflow_dispatch` only, so nothing is applied to the drill without a human dispatch.

- Input `mode`: `gate` (default) or `explore`.
  - `gate`: the pre-merge validation. Short TTL (90 min sweeper backstop), `keep` ignored, ALWAYS torn down once apply was attempted. Posts commit status `drill-gate` on the dispatched SHA (`github.sha`, the commit that is built and applied): `pending` at start, then `success` iff apply and smoke succeeded, otherwise `failure`.
  - `explore`: browse the drill (`ttl_minutes`, `keep`, `boot_logs` as before). Never posts a status.
- Branch protection on `main` requires status `drill-gate` (plus the existing CI checks). Any later push changes the PR head SHA, which has no `drill-gate`, so the merge is blocked again until someone re-dispatches the gate. This is intended: the gate always describes the exact commit that merges.
- The status reflects apply and smoke only. If teardown fails the workflow run fails but the status is unchanged; the sweeper (expires-at tag) is the backstop.
- Because a manual dispatch is itself a human action, the required reviewer on the `drill` environment (T-D96, ADR-0101) becomes optional (see `runbooks/github-settings.md`).

## Amendment 2026-11-16 (T-D125): prod releases come from GitHub releases

Superseded by [ADR-0109](0109-release-from-github-release-tags.md) for the release trigger: `release.yml` runs when a GitHub release (tag `vMAJOR.MINOR.PATCH`, commit on `main`) is published, not on every push to `main`. The "prod only from `main`" ref guards now read "`main`, or a `v*` tag whose commit is an ancestor of `main`". The `prod` environment approval, the PR gate and the credentials model are unchanged.

## Amendment 2026-11-18 (T-D147): non-deploy PRs skip the real gate

Amended by [ADR-0121](0121-drill-gate-skip-for-non-deploy-prs.md): a PR whose changed files are all on a non-deploy allowlist gets `drill-gate` set to success by `drill-gate-skip.yml` without a drill VM. Every other PR still needs the real gate run.

## Amendment 2026-11-21 (T-Q239, Q-041 / H1-03): the merge gate is tamper-resistant

Finding: the `protect-main` ruleset's required status checks carry no `integration_id`, so any actor able to post a commit status or check run with the right name (a workflow in a PR branch, a PAT) satisfies `drill-gate` and the CI contexts; and a PR can edit the workflows that produce those checks. Evidence: `docs/plans/quality-audit/repro/H1/gh_api/ruleset_protect_main.json`.

Decisions (ruleset edits are made by the operator; the repository half is `.github/CODEOWNERS` plus a guard):

1. **Required workflows from `main`.** The `protect-main` ruleset gains a `workflows` rule (required workflows) pinned to `ci.yml` at ref `refs/heads/main`, so the CI that gates a PR is the one on `main`, not the one in the PR branch.
2. **`integration_id` on every required status check context.** Each of `just ci (Python 3.12, ubuntu-latest)`, `drill-gate`, `uv lock --check`, `pip-audit (uv.lock)`, `trivy fs (repo)`, `trivy image (rising-dough:scan)` is bound to `integration_id` 15368 (GitHub Actions), so only the Actions app can satisfy it. `drill-gate` and `drill-gate-skip` are posted with `GITHUB_TOKEN`, which is that app.
3. **CODEOWNERS over the trust boundary**: `.github/`, `scripts/ci/`, `terraform/`, `tests/architecture/ci_environments.toml`, `tests/architecture/allowlists/workflow_trust.toml`. It documents the boundary and auto-requests the owner's review; `tests/architecture/test_codeowners.py` fails if the file or a path rule disappears. **"Require review from Code Owners" is NOT enabled yet** (OQ-24): GitHub never lets a PR author approve their own PR, so with a single maintainer it would make every PR touching these paths unmergeable. Enable it once a second reviewer or a review bot exists.
4. **Until then**, tamper-resistance comes from decisions 1 and 2 (required workflows from `main` plus `integration_id` 15368 on every required context). Repository-admin bypass stays as the operator's merge path; every bypass is recorded and visible in the ruleset's bypass log (Settings > Rules > Rulesets > `protect-main` > Rule insights, filter "Bypassed"; or Settings > Rules > Insights). Review that log after any merge that touched the CODEOWNERS paths.

Operator checklist: [`runbooks/github-settings.md`](../plans/v3/runbooks/github-settings.md) section 3c. Relates to ADR-0121, ADR-0132.

## Amendment 2026-11-21 (T-Q238, Q-040 / H1-02): signed-image identity pinned to `main`; rollback to `sha-*` needs ancestry

Finding: the host agent's cosign `identity_regexp` ended at `build.yml@`, so a signature produced by `build.yml` run from any ref (a drill gate build of an arbitrary branch pushes `sha-<short>` too) was accepted on prod. Evidence: `docs/plans/quality-audit/repro/H1/gate_and_signing_probe.out` section 2 and 5.

Decisions:

1. **Verified signing identity.** On prod the agent accepts a signature only when the certificate identity is `build.yml@refs/heads/main` or `build.yml@refs/tags/v<release>` of this repository (`terraform/modules/compute/user_data.tf`, `local.cosign_identity_regexp`). Drill hosts set `allow_branch_builds` (root: `env == "drill"`) and accept `refs/(heads|tags)/.+` of the same workflow, so a drill can still run an image built from the PR branch; that variable is the only widening and prod can never receive it (`terraform test` asserts both renders).
2. **Rollback to a `sha-*` tag (operator decision, OQ-24, 2026-11-21).** A `sha-*` image may run on prod ONLY if (a) its signature identity is `build.yml` on `refs/heads/main` (decision 1) AND (b) its commit is an ancestor of `main`. The host agent enforces (b) itself (`bp_agent.verify_main_ancestry`, GitHub compare API `main...<sha>`, status `behind` or `identical`), after the cosign check and before any file is written; an unreachable API fails closed (`ancestry_check`), a diverged or ahead commit is rejected (`ancestry_not_main`). Release-tag images are covered by decision 1 plus ADR-0109. Images signed from any other ref are rejected. The repository must be readable without authentication for the compare call; if it ever becomes private, rollback to a bare `sha-*` fails closed and a release tag (or an agent token) is needed.
3. **Drill-gate skip classifier** is docs only; its verdict is bound to the head SHA (see ADR-0121 amendment 2026-11-21).

Removes the `cosign-identity-unpinned` entry from `tests/architecture/allowlists/workflow_trust.toml`; the G17a guard also reads the `cosign_ref_regexp_prod` local. Relates to ADR-0100, ADR-0109, ADR-0111, ADR-0121.
