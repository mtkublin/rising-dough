# ADR-0149: The Drill Gate Upgrades a Running Host From the Prod Version

- **Status**: Accepted (2026-11-23; implementation T-Q306)
- **Date**: 2026-11-23
- **Amends**: [ADR-0099](0099-release-and-environment-policy.md) (PR merge gate; replaces the interim note of the 2026-11-22 T-Q305 amendment)
- **Relates to**: [ADR-0071](0071-production-startup-migrations.md) §3–§4, [ADR-0111](0111-terraform-declared-host-state.md), [ADR-0115](0115-drill-vm-is-exclusive-drill-lock.md), [ADR-0121](0121-drill-gate-skip-for-non-deploy-prs.md), [ADR-0127](0127-safe-prod-vm-replacement.md) §7, [ADR-0132](0132-ci-environments-split-by-data-sensitivity.md), [ADR-0135](0135-per-drill-age-keypair-in-terraform.md)
- **Task**: T-Q306 (re-scoped)

## Context

- A `mode=gate` drill boots a **fresh** VM with the PR head and smoke-tests it. Prod never does that: a release changes the image ref (and the host-state templates) on a VM that is already running, with data, and the host agent converges in place (ADR-0111).
- Bugs that pass a fresh boot and fail an in-place upgrade have reached prod:
  - v3.1.0 (T-Q305): adding `ipam` to the existing `edge` network cannot be applied while Caddy is attached; the release and its rollback both failed, prod was down 17 min.
  - T-D127: cloud-init does not re-run on a running VM, so a fixed deploy script never reached prod (break-glass).
  - T-D115: the `docker` group fix landed in cloud-init only; the running prod VM needed a manual `usermod`.
  - T-D158: the prod agent predated the drain the release relied on; drills always ran the new agent.
- The ADR-0099 amendment of 2026-11-22 added a unit guard for one case (same-name compose network changes) and recorded the upgrade drill as T-Q306, with the open question whether it should become the default gate.
- The "latest `v*` tag" is not always what prod serves: v3.1.1 was tagged but never deployed. GitHub records each `prod` environment deployment with its ref and a status (`deployments?environment=prod`).
- ADR-0132 forbids prod-read material on a host that runs unmerged code, and `prod-restore-read` is `main`-only with an approval. A PR gate cannot restore the prod replica.

## Decision

1. **`mode=gate` becomes an upgrade drill.** No separate mode. Every real gate run (PRs that ADR-0121 does not skip) runs the phases below on **one** drill VM, inside the existing drill lock and `drill` concurrency group. `mode=explore` stays a fresh boot of the dispatched ref.
2. **Baseline = the version prod serves.** The ref is the newest deployment to the GitHub `prod` environment whose latest status is `success` (not the latest tag). The workflow resolves the tag's image digest from GHCR and fails closed when there is no such deployment, the tag is not an ancestor of `origin/main`, or the image is gone. The baseline is the tag's **Terraform and templates** (`terraform/` at the tag: cloud-init, compose template, host agent) plus its signed image; only the drill tooling (`.github/`, `scripts/ci/`) comes from the PR head. Inputs that the tag's Terraform does not declare reach it only as `TF_VAR_*`, which Terraform ignores.
3. **Phase 1 — baseline.** Apply the baseline with `drill_allow_empty_db=true` and wait for the host status and `/ready`.
4. **Seed — demo data through the restore path.** A drill-only helper `seed-demo`, modelled on `restore-from-prod` (ADR-0034 §5): it stops `app` and `litestream`, moves the empty DB aside, installs `data/demo.sqlite` **from the baseline tag** (so its schema is at most the tag's), runs `PRAGMA integrity_check`, fixes ownership, starts `litestream` and `app` (the tag's entrypoint applies any pending migrations, ADR-0071) and waits for `/ready`. The workflow then writes the marker rows (`scripts/ci/rehearsal_marker.sh`), waits until Litestream has shipped them to the drill bucket and records the generation. No prod data: the demo DB is anonymized and tracked in git, the drill bucket and age pair are per-drill (ADR-0135), so ADR-0132 is unchanged.
5. **Phase 2 — upgrade to the PR head.** A marker writer commits one row per second and tolerates errors while the app restarts. Apply the PR head's Terraform and image on the same drill. The gate first decides the expected path from the PR plan (`host_release.py replaced`):
   - **In place** (expected for most PRs): `server_replaced` must be `false`. Wait for the agent to converge on the PR ref and for `/ready`, stop the writer, then check that every committed marker row is present, the Litestream generation is the seeded one (replication continued across the restart) and `PRAGMA integrity_check` is `ok`.
   - **Replacement** (the PR plan replaces the VM): `server_replaced` must be `true`, and the gate runs the replacing path exactly as prod does (drain, apply, `wait --require-restore`). It then verifies as `replace-rehearsal.yml` does: restore report `restored` with the seeded generation, 0 lost committed rows, integrity `ok`, tailnet cleanup and rename (ADR-0127 §7).
   - A plan that contradicts the detection fails the gate.
6. **Phase 3 — rollback.** In-place path only: roll back through `terraform.yml` with `rollback: true` on the drill (the image goes back to the baseline ref and the PR's templates stay, as in a prod rollback, ADR-0111), then require host status, `/ready` and integrity `ok`. This proves ADR-0071 §4 (N-1 schema) and the T-Q305 case (rollback with the new template). The replacement path skips phase 3, because `release.yml` does not roll the image back after a replacement (ADR-0127).
7. **Verdict.** `drill-gate` is `success` only if every phase that ran passed. The failure description names the phase (`baseline`, `seed`, `upgrade`, `rollback`), so a failing baseline is not read as a PR fault. It is still a failure, because the gate fails closed. Teardown always runs (ADR-0115).

## Consequences

- The gate now covers the fresh-vs-upgrade class (template, agent, migration, replication and rollback changes) for the exact version step the next release takes from prod.
- **Accepted risk (operator, 2026-11-23): releases bundle PRs.** Each PR is gated as prod → PR, but a release goes from prod to `main` with every unreleased merge. No drill runs on the release candidate (`release.yml` keeps no drill stage, T-D90).
- **Known limit (operator, 2026-11-23): host drift is not reproduced.** The prod VM ran cloud-init from the version that created it, which may predate the baseline tag. The baseline is a fresh boot of the tag. The long-term fix is to keep host state out of cloud-init (ADR-0111 direction), not this gate.
- **The PR head no longer gets a fresh boot in the gate.** That path is exercised by the replacement branch (when the PR replaces the VM), by `mode=explore`, by `replace-rehearsal.yml`, and by the monthly `restore-drill.yml` on `main`. A cloud-init regression that does not replace the VM can merge and surface only at the next replacement, DR or restore drill (at most a month after the merge).
- **Cost (accepted, operator 2026-11-23).** One VM per gate, as today. The run is longer by a seed, an in-place converge with the writer, and a rollback converge. The 5 green gates before 2026-11-23 took 11–18 min. The added time is not measured yet: record it on the first runs in T-Q306. The longer drill lock means PRs queue longer. The ADR-0121 docs-only skip is unchanged. The gate's TTL must cover the longer run (sweeper backstop).
- Depends on the GHCR retention keeping every `v*` image (`image-retention.yml` keeps `v*` tags) and on GitHub deployment records for `prod` (created by the `prod` environment job). A break-glass change on the prod host is not reflected in the record.
- The T-Q305 unit guard (`test_compose_upgrade_in_place.py`) stays as the cheap pre-check.

## Alternatives rejected

- **Restore the prod replica as the seed** (`restore-drill.yml` mechanism with prod data): it needs `prod-restore-read` (`main`-only, approval) on a PR branch and would put prod data on a host running unmerged code. ADR-0132 / H4-03 removed exactly that.
- **Baseline = latest `v*` tag:** a tag that never deployed (v3.1.1) would hide the real step.
- **A separate `mode=upgrade`, opt-in or only for `terraform/` PRs:** a compose or agent change can arrive through `deploy/` or `scripts/`. A path rule would be a second, weaker classifier next to ADR-0121.
- **Upgrade drill on the release candidate instead of per PR:** catches the bundle, but only after merge, and it adds a drill to every release. Rejected for now (accepted risk above).

## Implementation note 2026-11-23 (T-Q306b)

`terraform.yml` gains the optional `workflow_call` input `terraform_ref` (string, default empty = unchanged behaviour). When set, the `apply` job checks out `refs/tags/<terraform_ref>` into `terraform-baseline/` and replaces `terraform/` with the tag's copy, keeping `terraform/scripts/` (the CI helpers `check_tf_vars.py`, `mask_plan.py`) at the workflow ref; `scripts/ci/*` and the composite actions are untouched. It is drill-only and fails closed: a guard step before any checkout refuses `env=prod` and any value that is not a `vMAJOR.MINOR.PATCH` tag. The workflow passes every Terraform input as `TF_VAR_*` env, never as a `-var` flag (a unit test asserts it), so inputs the tag's Terraform does not declare are ignored rather than rejected. `drill.yml` does not use the input yet.

## Implementation note 2026-11-23 (T-Q306d/e)

`drill.yml` `mode=gate` runs the phases as jobs: `baseline` (resolve, `prod_baseline.py`) → `apply-baseline` (`terraform_ref` = the tag, image = the tag's digest, `drill_allow_empty_db=true`) → `smoke-baseline` → `seed` → `detect` (a plan of the PR head against the baseline state in the ungated `drill-plan` environment, `host_release.py replaced`) → `writer-started` / `writer` → `apply-upgrade` → `converge` → `verify` → `apply-rollback` → `verify-rollback` → `teardown` (always once an apply was attempted).

- **Seed delivery.** The baseline host runs the tag's Terraform, which does not install `seed-demo`. The `seed` job renders this PR's `seed-demo.tpl` with `scripts/ci/render_seed_demo.py` (the two template variables, `$${` unescaped), writes it to `/tmp/seed-demo.sh` over ssh stdin (not `bash -s`: a docker command could read the rest of the script) and runs it with the demo DB read from the baseline tag (`git show <tag>:data/demo.sqlite`, copied over ssh stdin). It then asserts `accounts`, `transactions` and `categories` are non-empty (T-Q302), writes the marker rows and records the Litestream generation.
- **Writer.** `rehearsal_marker.sh writer-until` keeps inserting through app restarts until `stop` creates a stop file (in place) or the host disappears (replacement, ssh exit 255); the step runs under `set +e` (T-D156). The verdict does not wait for it; `teardown` does not wait for it either, because in a failed run it ends only when the host is destroyed.
- **Detection** is a real plan; `converge` fails the gate when the apply's `server_replaced` differs. Replacement path: drain and `--require-restore` as in `terraform.yml`, tailnet cleanup and rename, restore report with the seeded generation, 0 lost rows, integrity. In-place path: generation unchanged, all rows, integrity, then the rollback phase.
- **Verdict.** `gate-result` posts `success` only when every phase job that ran succeeded (rollback jobs are required on the in-place path and skipped by design on a replacement). A failure names the first failing phase (`ci/build`, `baseline`, `seed`, `upgrade`, `rollback`) within 140 characters.
- **TTL** for the gate is 240 minutes (was 90): three gated applies plus the longer run; the real run time is not measured yet and is to be tightened after the first runs (T-Q306).
- The gate now needs up to three approvals of the gated `drill` environment (baseline, upgrade, rollback applies), plus the SSH jobs if `drill` is gated for them as well.
- **Amendment 2026-11-23 (T-Q306f).** The last bullet is stale: the `drill` environment has no required reviewers today, so the gate needs no approvals. First measured run: 22 min 24 s (run 45247014045, in-place path); the 240 min TTL stays a generous backstop. `detect` names its secrets explicitly (`toJSON(secrets)` in a dispatched workflow's own job aborts the dispatch with `action_required`). Runbook: `docs/plans/v3/runbooks/deploy.md`, "What the drill gate proves".
