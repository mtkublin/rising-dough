# v3 go-live operator checklist (as of 2026-11-18)

## State as of 2026-11-18

- Prod is live at https://budget.rising-dough.eu and runs `sha-89ac3c2`, moved there by a logged break-glass after the first pipeline release's SSH deploy failed (T-D127, ADR-0111 Context).
- v3 and the follow-ups (T-D124..T-D132) are on `main` (PR #2, PR #14). T-D124 drill tailnet cleanup proven 2026-11-17.
- Steps 1-11, 11a and 11b are done. Step 10a: the agent bootstrap is installed on prod (2026-11-18). Release `v3.0.0` stopped in the apply job's "Guard env / ref" step, before any `terraform init`/`apply`, so prod is unchanged. Fixed by T-D134 (PR #16, merged 2026-11-18).
- Next, in order:
  1. Release `v3.0.1` after the T-D134 fix (the `v*` tags are immutable, step 11a, so `v3.0.0` cannot be re-cut), approve the apply, and finish 10a. Rollback target if it fails: `sha-89ac3c2`.
  2. First restore drill (T-D40), before 2026-12-01 03:00 UTC. `restore-drill.yml` has never run and the monthly cron would make that first run unattended. Dispatch it from `main` after step 1 and watch it. It closes T-D40, the first-run gap in T-D41, and the T-D56 drill acceptance. Delete plaintext Litestream generations only after it is green (T-D56).
  3. After the release: delete the dead deploy secrets (`github-settings.md`), 11c retention, re-run Observatory (T-D42, T-D132), delete `/data/pre-seed-*` on prod. T-D45 done 2026-11-18.
  4. On the next explore drill: repeat T-D33 (the `failed` state and reconvergence were not observed), confirm T-D135 (passkeys with the localhost RP defaults), and after the T-D135 fix run the T-D43 smoke journey there. T-D43 never runs on prod (decision 2026-11-18).
- ADR-0099 is in force: no laptop applies against prod, except break-glass ([`break-glass.md`](break-glass.md)) and the bootstrap stacks.

Never write secrets, key ids or passwords into the repo, a PR or a chat while doing these steps.

## Checklist

### 1. GitHub CLI and repo visibility
- [x] **Where:** laptop + GitHub UI.
- Run `gh auth login`. Check whether the repo is private: required reviewers on environments need GitHub Pro/Team for private repos.
- **Done when:** `gh auth status` is green and you know whether environment required reviewers are available.
- Runbook: [`github-settings.md`](github-settings.md).

### 2. Tailscale admin console
- [x] **Where:** Tailscale admin console.
- Enable MagicDNS and HTTPS Certificates.
- ACL: `tag:ci -> tag:drill:443`, plus your own devices -> `tag:drill:443` (see [`tailscale-acl.hujson`](tailscale-acl.hujson)).
- OAuth client: single-client model, `tag:automation` owns `tag:prod`, `tag:drill`, `tag:ci`.
- Remove any stale `budget-planner-drill` node (T-D107).
- **Done when:** the ACL is saved, HTTPS certs show enabled, the OAuth client exists, and no stale drill node is listed.
- Runbook: [`tailscale-ssh.md`](tailscale-ssh.md).

### 3. Bootstrap 3a (`terraform/bootstrap`)
- [x] **Where:** laptop, with the admin key from `scw config` (ADR-0096 exception).
- Re-run the plan; the saved plan was session-scratch and is gone.
- Expect 2 to add: drill state bucket `budget-planner-tfstate-drill-pl-waw` + ACL. Review, then apply.
- Commit `terraform/bootstrap/terraform.tfstate` (it holds no secrets).
- **Done when:** apply reports 2 added, nothing else changed, and the state file is committed.
- Runbooks: [`break-glass.md`](break-glass.md), [`key-rotation.md`](key-rotation.md).

### 4. Bootstrap 3b (`terraform/bootstrap/ci`)
- [x] **Where:** laptop.
- T-D103 decided (ADR-0104): this stack now also owns the prod app identity, the drill app identity and the restore-reader. `ci-prod`/`ci-drill` have no IAMManager.
- `terraform init`, then **import the prod IAM before the first apply** (runbook section "Import the env-stack IAM into bootstrap/ci", steps 1-3). The plan must show creates only and no change under `module.app_prod` / `module.restore_reader`.
- Apply locally.
- Keep the local state file (holds key secrets, gitignored) on the FileVault-encrypted laptop. Off-laptop backup optional (2026-11-16: operator skipped; recovery = re-import, `key-rotation.md`).
- Verify the drill state bucket policy principals.
- **Done when:** `ci-prod`, `ci-drill`, `ci-plan` keys and `module.app_drill` exist, the prod IAM is imported unchanged, and bucket policy principals are as intended.
- Runbook: [`key-rotation.md`](key-rotation.md).

### 5. GitHub environments
- [x] **Where:** GitHub UI.
- Create environments: `prod` (required reviewer), `prod-plan`, `drill`, `drill-plan`, `drill-teardown`.
- Add secrets per environment, using the CI keys from step 4.
- Add vars `TAILNET_DNS_NAME`, `MANAGED_DNS_ZONE=true`, `BUCKET_ADMIN_PRINCIPALS`, `APP_DOMAIN=rising-dough.eu`.
- The age identity, GHCR PAT and Tailscale values must be EXACTLY the values in the local `terraform/.env`, or prod will diverge.
- Settle the deploy-key question (T-D109) here.
- Add the ADR-0104 secrets: `APP_APPLICATION_ID`, `APP_SCW_ACCESS_KEY`, `APP_SCW_SECRET_KEY` (all five environments, per-env values) and `RESTORE_READER_APPLICATION_ID` (`prod`, `prod-plan`). The prod app key and the restore-reader key are read once from the prod state (`key-rotation.md` part 2, steps 5-6); do it before step 11. <!-- pragma: allowlist secret -->
- **Done when:** every environment matches the table in the runbook.
- Runbook: [`github-settings.md`](github-settings.md).

### 6. Remove duplicate repo-level secrets
- [x] **Where:** GitHub UI.
- Delete repo-level secrets now covered by environment secrets.
- **Done when:** Settings -> Secrets shows no duplicates of environment secrets.
- Runbook: [`github-settings.md`](github-settings.md).

### 7. Credential cleanup
- [x] **Where:** Scaleway console + laptop.
- Delete the old leaked Scaleway Owner-role API key in the Scaleway console (it was pasted into a chat transcript on 2026-11-04).
- Delete that transcript file from `~/.claude/projects/...`.
- After all bootstrap work: `scw config unset access-key` and `scw config unset secret-key`; remove the admin key from shell history. The admin key lives only in the password manager.
- **Done when:** the old key no longer appears in the console, the transcript is gone, and `scw config` holds no keys.
- Runbook: [`key-rotation.md`](key-rotation.md).

### 8. Leftover public drill DNS
- [x] **Where:** Scaleway console (as org admin).
- Delete any `drill.budget...` records in the `rising-dough.eu` zone (drill is tailnet-only, ADR-0101).
- **Done when:** the zone has no drill records.
- Runbook: [`drill.md`](drill.md).

### 9. Fix PR checks, push, run the first gate
- [x] **Where:** laptop + GitHub UI. Done 2026-11-16: `drill-gate` success on `ec01640` (run 43907146399), after T-D121/T-D122/T-D123.
- Merge the T-D99 / T-D101 fixes and push v3.
- First merge PR #3 (T-D121): `drill.yml` must exist on `main` before GitHub accepts a dispatch.
- Run `gh workflow run drill.yml --ref v3 -f mode=gate` (no approval: the `drill` environment has no reviewer).
- **Done when:** commit status `drill-gate` is `success` on the v3 head. Confirm the tailnet certificate behavior (T-D107).
- Runbook: [`drill.md`](drill.md).

### 10. Protect `main`
- [x] **Where:** GitHub UI.
- Branch protection or a ruleset on `main` requiring `drill-gate` plus the CI checks.
- **Done when:** a PR without a green `drill-gate` cannot merge.
- Runbook: [`github-settings.md`](github-settings.md).

### 11. Merge the PR: first GitHub release
- [x] **Where:** GitHub UI.
- Done 2026-11-16: PR #2 merged, apply green; the SSH deploy failed (T-D127), so prod reached `sha-89ac3c2` by break-glass (CHANGELOG). The next release goes through the host agent (10a).
- Merge v3 into `main`. This is the first GitHub release: ci -> build -> tf-apply-prod (one approval). It also ships the cryptography fix.
- **Done when:** the release run is green and prod serves a newer image than `sha-075f986`.
- Runbooks: [`deploy.md`](deploy.md), [`rollback.md`](rollback.md) if it goes wrong.

### 10a. Migrate prod to the host agent (ADR-0111, T-D129f)
- [ ] **Where:** your workstation (tailnet) + GitHub UI, after T-D129 is on `main` and before the next release.
- ~~Create the `prod-deploy` environment (ADR-0110)~~: superseded; the release is the approved apply, there is no deploy job.
- 2026-11-18: bootstrap installed (script run, timer and guard active). Release `v3.0.0` blocked before prod (T-D134); finish with `v3.0.1`.
- Follow [`host-state-migration.md`](host-state-migration.md): install the agent bootstrap on the prod VM (one script, logged), cut the release, then delete `prod-deploy` and the deploy secrets.
- **Done when:** the release run is green with `converged: …` and `/.well-known/bp-deploy-status.json` reports state `ok`.

### 11a. Tag ruleset on `v*` (ADR-0109, T-D125)
- [x] Done 2026-11-16 (rulesets `release-tags-create`, `release-tags-immutable`). **Where:** GitHub UI, before cutting the first release after the T-D125 merge.
- Create the tag ruleset as described in [`github-settings.md`](github-settings.md) section 3b.
- The merge that brings T-D125 is the last merge-triggered release. From then on prod releases come from `gh release create vX.Y.Z --target main` ([`deploy.md`](deploy.md)).
- **Done when:** the ruleset is active on `v*`.

### 11b. Drop ci-prod's transitional IAM read access (ADR-0104)
- [x] **Where:** laptop.
- After the release in step 11 has applied (its plan showed `module.iam` and `module.restore_reader` as no longer managed, nothing destroyed): `terraform apply -var ci_prod_iam_transition=false` in `terraform/bootstrap/ci`.
- **Done when:** `ci-prod`'s policy has no organization rule and a prod PR plan still succeeds.
- Runbook: [`key-rotation.md`](key-rotation.md) part 2, step 7.

### 11c. Enable GHCR image retention (T-D126)
- [ ] **Where:** GitHub UI (package settings, Actions) and laptop.
- Package link: already in place (2026-11-18: the repo has Admin under package settings > Manage Actions access by default, which covers Write). After the first release: dispatch `image-retention` once with `dry_run=true`, review, then set repo variable `IMAGE_RETENTION_ENABLED=true`.
- **Done when:** a scheduled or `dry_run=false` run shows `mode: APPLY` and the next release still deploys.
- Runbook: [`image-retention.md`](image-retention.md).

### 12. Open question for the user
- [x] Skipped 2026-11-16: the user does not remember the cut-off message "Also, once drill is deployed by"; nothing recorded.

## Related tasks

T-D99 and T-D101 to T-D109 in [`../tasks.md`](../tasks.md).
