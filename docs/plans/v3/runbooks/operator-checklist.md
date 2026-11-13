# v3 go-live operator checklist (as of 2026-11-07)

## State as of 2026-11-07

- Prod is live at https://budget.rising-dough.eu. It was brought up from the laptop, the one-time ADR-0099 exception.
- The local DB is seeded to prod ([`prod-db-seed.md`](prod-db-seed.md)).
- Drill is destroyed.
- v3 is pushed, with an open PR v3 -> main. The Terraform and Security workflows fail on that PR (T-D99, T-D101).
- ADR-0099 is in force: no laptop applies against prod from now on, except break-glass ([`break-glass.md`](break-glass.md)).
- Prod still runs image `sha-075f986`, so it lacks the cryptography fix until the first GitHub release (step 11).

Never write secrets, key ids or passwords into the repo, a PR or a chat while doing these steps.

## Checklist

### 1. GitHub CLI and repo visibility
- [ ] **Where:** laptop + GitHub UI.
- Run `gh auth login`. Check whether the repo is private: required reviewers on environments need GitHub Pro/Team for private repos.
- **Done when:** `gh auth status` is green and you know whether environment required reviewers are available.
- Runbook: [`github-settings.md`](github-settings.md).

### 2. Tailscale admin console
- [ ] **Where:** Tailscale admin console.
- Enable MagicDNS and HTTPS Certificates.
- ACL: `tag:ci -> tag:drill:443`, plus your own devices -> `tag:drill:443` (see [`tailscale-acl.hujson`](tailscale-acl.hujson)).
- OAuth client: single-client model, `tag:automation` owns `tag:prod`, `tag:drill`, `tag:ci`.
- Remove any stale `budget-planner-drill` node (T-D107).
- **Done when:** the ACL is saved, HTTPS certs show enabled, the OAuth client exists, and no stale drill node is listed.
- Runbook: [`tailscale-ssh.md`](tailscale-ssh.md).

### 3. Bootstrap 3a (`terraform/bootstrap`)
- [ ] **Where:** laptop, with the admin key from `scw config` (ADR-0096 exception).
- Re-run the plan; the saved plan was session-scratch and is gone.
- Expect 2 to add: drill state bucket `budget-planner-tfstate-drill-pl-waw` + ACL. Review, then apply.
- Commit `terraform/bootstrap/terraform.tfstate` (it holds no secrets).
- **Done when:** apply reports 2 added, nothing else changed, and the state file is committed.
- Runbooks: [`break-glass.md`](break-glass.md), [`key-rotation.md`](key-rotation.md).

### 4. Bootstrap 3b (`terraform/bootstrap/ci`)
- [ ] **Where:** laptop.
- T-D103 decided (ADR-0104): this stack now also owns the prod app identity, the drill app identity and the restore-reader. `ci-prod`/`ci-drill` have no IAMManager.
- `terraform init`, then **import the prod IAM before the first apply** (runbook section "Import the env-stack IAM into bootstrap/ci", steps 1-3). The plan must show creates only and no change under `module.app_prod` / `module.restore_reader`.
- Apply locally.
- Store the local state file (holds key secrets, gitignored) in the password manager.
- Verify the drill state bucket policy principals.
- **Done when:** `ci-prod`, `ci-drill`, `ci-plan` keys and `module.app_drill` exist, the prod IAM is imported unchanged, the state file is in the password manager, and bucket policy principals are as intended.
- Runbook: [`key-rotation.md`](key-rotation.md).

### 5. GitHub environments
- [ ] **Where:** GitHub UI.
- Create environments: `prod` (required reviewer), `prod-plan`, `drill`, `drill-plan`, `drill-teardown`.
- Add secrets per environment, using the CI keys from step 4.
- Add vars `TAILNET_DNS_NAME`, `MANAGED_DNS_ZONE=true`, `BUCKET_ADMIN_PRINCIPALS`, `APP_DOMAIN=rising-dough.eu`.
- The age identity, GHCR PAT and Tailscale values must be EXACTLY the values in the local `terraform/.env`, or prod will diverge.
- Settle the deploy-key question (T-D109) here.
- Add the ADR-0104 secrets: `APP_APPLICATION_ID`, `APP_SCW_ACCESS_KEY`, `APP_SCW_SECRET_KEY` (all five environments, per-env values) and `RESTORE_READER_APPLICATION_ID` (`prod`, `prod-plan`). The prod app key and the restore-reader key are read once from the prod state (`key-rotation.md` part 2, steps 5-6); do it before step 11. <!-- pragma: allowlist secret -->
- **Done when:** every environment matches the table in the runbook.
- Runbook: [`github-settings.md`](github-settings.md).

### 6. Remove duplicate repo-level secrets
- [ ] **Where:** GitHub UI.
- Delete repo-level secrets now covered by environment secrets.
- **Done when:** Settings -> Secrets shows no duplicates of environment secrets.
- Runbook: [`github-settings.md`](github-settings.md).

### 7. Credential cleanup
- [ ] **Where:** Scaleway console + laptop.
- Delete the old leaked Scaleway Owner-role API key in the Scaleway console (it was pasted into a chat transcript on 2026-11-04).
- Delete that transcript file from `~/.claude/projects/...`.
- After all bootstrap work: `scw config unset access-key` and `scw config unset secret-key`; remove the admin key from shell history. The admin key lives only in the password manager.
- **Done when:** the old key no longer appears in the console, the transcript is gone, and `scw config` holds no keys.
- Runbook: [`key-rotation.md`](key-rotation.md).

### 8. Leftover public drill DNS
- [ ] **Where:** Scaleway console (as org admin).
- Delete any `drill.budget...` records in the `rising-dough.eu` zone (drill is tailnet-only, ADR-0101).
- **Done when:** the zone has no drill records.
- Runbook: [`drill.md`](drill.md).

### 9. Fix PR checks, push, run the first gate
- [ ] **Where:** laptop + GitHub UI.
- Merge the T-D99 / T-D101 fixes and push v3.
- Run `gh workflow run drill.yml --ref v3 -f mode=gate` and approve the `drill` environment.
- **Done when:** commit status `drill-gate` is `success` on the v3 head. Confirm the tailnet certificate behavior (T-D107).
- Runbook: [`drill.md`](drill.md).

### 10. Protect `main`
- [ ] **Where:** GitHub UI.
- Branch protection or a ruleset on `main` requiring `drill-gate` plus the CI checks.
- **Done when:** a PR without a green `drill-gate` cannot merge.
- Runbook: [`github-settings.md`](github-settings.md).

### 11. Merge the PR: first GitHub release
- [ ] **Where:** GitHub UI.
- Merge v3 into `main`. This is the first GitHub release: ci -> build -> tf-apply-prod (approval) -> deploy-prod. It also ships the cryptography fix.
- **Done when:** the release run is green and prod serves a newer image than `sha-075f986`.
- Runbooks: [`deploy.md`](deploy.md), [`rollback.md`](rollback.md) if it goes wrong.

### 11b. Drop ci-prod's transitional IAM read access (ADR-0104)
- [ ] **Where:** laptop.
- After the release in step 11 has applied (its plan showed `module.iam` and `module.restore_reader` as no longer managed, nothing destroyed): `terraform apply -var ci_prod_iam_transition=false` in `terraform/bootstrap/ci`.
- **Done when:** `ci-prod`'s policy has no organization rule and a prod PR plan still succeeds.
- Runbook: [`key-rotation.md`](key-rotation.md) part 2, step 7.

### 12. Open question for the user
- [ ] The message "Also, once drill is deployed by" was cut off and never completed. Finish the thought so it can be recorded as a task.

## Related tasks

T-D99 and T-D101 to T-D109 in [`../tasks.md`](../tasks.md).
