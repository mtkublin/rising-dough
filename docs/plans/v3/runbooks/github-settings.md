# Runbook: GitHub settings checklist (manual, ADR-0099 / ADR-0100)

**Context.** These settings turn "prod only from main via Actions" into something the platform enforces. They cannot be set from Terraform in this repo; re-check them after any repo transfer and at each key rotation. Tick each box once, record the date at the bottom.

## 1. Environments (Settings > Environments)

- [x] **`prod`**: Required reviewers = you (and prevent self-review only if a second reviewer exists). Deployment branches and tags: **`main` and tag pattern `v*`** (the release runs from a `v*` tag, ADR-0109). Used by `tf-apply-prod` (the single approval per release, ADR-0110; the release is this apply, ADR-0111) and by the apply of `rollback.yml` (env prod). Holds all Scaleway write credentials (ADR-0100).
  - Check the tag rule (T-D134; missing until 2026-11-18, it blocked release `v3.0.0`): `gh api repos/mtkublin/rising-dough/environments/prod/deployment-branch-policies --jq '.branch_policies[]|"\(.type) \(.name)"'` must list `branch main` and `tag v*`.
- [ ] **No `prod-deploy`** (ADR-0111, T-D129): the SSH deploy job is gone; a release is the approved `prod` apply. The environment was never created (checked 2026-11-16); if it exists, delete it. Once T-D129 is on `main`, delete the deploy secrets from `prod` (`DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, `PROD_HOST`, variable `PROD_URL`).
- [ ] **`prod-plan`** (ungated, used by PR plan leg and `key-expiry.yml`): no reviewers; deployment branches: all branches. It must hold only the **read-only** `ci-plan` key (ADR-0100). Never put write credentials or Litestream/age identities that decrypt prod data here beyond what the plan needs.
- [ ] **`drill`** (apply; reviewer OPTIONAL since T-D98): drill.yml now starts only from a manual `workflow_dispatch`, which is already a human action. For a single-maintainer repository we recommend **no required reviewers** (the approval would only be you approving yourself). If you add Required reviewers (a second maintainer exists), every drill apply waits for approval. Deployment branches and tags: selected `main` plus the branches you dispatch gates from (or all branches, since only dispatch can start the drill and branch protection governs merges). Used only by the `apply` job of `terraform.yml` for drill and by `restore-drill.yml`.
- [ ] **`drill-teardown`** (ungated, ADR-0101): no reviewers; deployment branches: all branches. Used by every drill destroy path (`drill-sweeper.yml` scan + destroy, `drill-destroy.yml`, the `teardown` job of `drill.yml`) and by the drill `smoke` job, the restore drill's `drill-lock`, `verify-destroy` and `report` jobs and the reusable `tailnet-cleanup.yml`, so teardown never waits for approval. Holds the same drill secrets and variables as `drill` (section 2) except `DEPLOY_SSH_PRIVATE_KEY`, which lives only in `drill` (the restore drill's `restore-drill` job runs there).
- [x] **`prod-tailnet`** (ungated, T-D155, ADR-0122; created 2026-11-18, both secrets set 2026-11-18): no reviewers (the release apply was already approved); deployment branches and tags: **`main` and tag pattern `v*`** only. Used only by `tailnet-cleanup.yml` with `env: prod` (job `tailnet-cleanup-prod` of `release.yml`, after a release that replaced the VM). Holds only `TS_CLEANUP_CLIENT_ID` / `TS_CLEANUP_SECRET` of `budget-planner-prod-cleanup` (section 4). Without it the cleanup warns and the operator removes the node by hand (`deploy.md`).
- [ ] **`drill-plan`** (ungated, ADR-0101): no reviewers; deployment branches: all branches. Used by the drill leg of the PR plan in `terraform.yml` (mirrors `prod-plan`). Same drill secrets as `drill`.
- Private repositories: **Required reviewers on environments need GitHub Pro/Team** (or an org plan); on the free plan the setting is unavailable. Not needed with the recommended no-reviewer setup.
- Only relevant if reviewers are configured on `drill`: a run waiting for approval holds the `drill` concurrency group, so the sweeper and `drill-destroy.yml` queue behind it. Approve or cancel pending drill runs promptly.
- [ ] Delete **repo-level** `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` (and any repo-level copy of the env secrets below) so a missing environment secret fails instead of falling back.

## 2. Secrets and variables per environment

Same names in every environment, different values (ADR-0093). The three drill environments (`drill`, `drill-teardown`, `drill-plan`) hold identical copies of the drill column; keep them in sync when rotating (`key-rotation.md`). Verified against `.github/workflows/*.yml`.

| Secret | `prod` | `prod-plan` | `drill`, `drill-teardown`, `drill-plan` | Notes |
|---|:-:|:-:|:-:|---|
| `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` | ci-prod | ci-plan (read-only) | ci-drill | outputs of `terraform/bootstrap/ci` |
| `SCW_DEFAULT_PROJECT_ID` | prod project | prod project | drill project | |
| `SCW_DEFAULT_ORG_ID` | x | x | x | also used by `key-expiry.yml` (prod-plan) |
| `ADMIN_EMAIL`, `APP_DOMAIN` | x | x | x | |
| `OPERATOR_SSH_PUBKEY` | x | x | x | `DEPLOY_SSH_PUBKEY` is unused since ADR-0111; delete it everywhere |
| `GHCR_PULL_PAT` | x | x | x | read:packages only |
| `LITESTREAM_AGE_IDENTITY`, `LITESTREAM_AGE_RECIPIENT` | x | x | x | per-env age keypair |
| `MANAGED_DNS_ZONE` (optional) | x | x | x | |
| `BUCKET_ADMIN_PRINCIPALS`, `BUCKET_READONLY_PRINCIPALS` (optional) | x | x | x | |
| `BUCKET_PLAN_PRINCIPALS` (ADR-0105: `["application_id:<ci-plan>"]`) | x | x | | |

ADR-0105: `BUCKET_ADMIN_PRINCIPALS` holds the operator **and** the env's apply identity: prod/prod-plan add `application_id:<ci-prod>`, drill envs add `application_id:<ci-drill>` (`terraform -chdir=terraform/bootstrap/ci output ci_application_ids`).
| `PROD_REPLICA_RO_ACCESS_KEY`, `PROD_REPLICA_RO_SECRET_KEY` | | | x | restore-reader of prod replica; drill only |
| `APP_APPLICATION_ID` | prod app | prod app | drill app | `bootstrap/ci` output `app_application_ids` (ADR-0104) |
| `APP_SCW_ACCESS_KEY`, `APP_SCW_SECRET_KEY` | prod app key | prod app key | drill app key | Litestream identity; prod values read once from prod state, then from `bootstrap/ci` after a rotation (`key-rotation.md`) |
| `RESTORE_READER_APPLICATION_ID` | x | x | | `bootstrap/ci` output `restore_reader_application_id`; prod only |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | prod client | prod client (plan reads only) | drill client | see section 4 |
| `DEPLOY_SSH_PRIVATE_KEY` | | | `drill` only | `restore-drill.yml` job `restore-drill` only (operator SSH over the tailnet; runs in env `drill`, T-D133); not in `prod`, `drill-teardown`, `drill-plan` (ADR-0111) |

| Variable | `prod` | `drill`, `drill-teardown`, `drill-plan` |
|---|:-:|:-:|
| `TAILNET_DNS_NAME` (ADR-0101), e.g. `tail1234.ts.net` (admin console > DNS; not a secret) | | x |

`drill.yml` no longer reads `DRILL_URL`: the drill has no public DNS (ADR-0101). It derives `https://budget-planner-drill-<run id>.${TAILNET_DNS_NAME}` and joins the tailnet as `tag:ci` for the smoke test.

Repo-level variable (T-D126): `IMAGE_RETENTION_ENABLED` (`true` lets the scheduled `image-retention.yml` delete; unset = dry run). Set to `true` on 2026-11-18 (operator). The `budget-planner` package must be linked to the repo with Actions access role Write ([`image-retention.md`](image-retention.md)). Otherwise none. `GITHUB_TOKEN` is automatic; Trivy SARIF uploads to Code Scanning use it (T-D120).

Unused since ADR-0111, deleted 2026-11-18 (user-approved; no workflow read them, checked by grep): [x] `DEPLOY_SSH_PUBKEY` (all envs), `DEPLOY_SSH_KNOWN_HOSTS`, `PROD_HOST`, `DEPLOY_SSH_PRIVATE_KEY` in `prod`, `DRILL_HOST` (all drill envs), variables `PROD_URL` (prod) and `DRILL_URL` (drill envs). Deleted: `DEPLOY_SSH_PUBKEY` in prod, drill, drill-plan, drill-teardown; `DEPLOY_SSH_KNOWN_HOSTS`, `PROD_HOST`, `DEPLOY_SSH_PRIVATE_KEY` in prod; `DRILL_HOST` in the three drill envs; variable `PROD_URL` (prod); variable `DRILL_URL` in the three drill envs. None existed at repo level. **`DEPLOY_SSH_PRIVATE_KEY` now exists only in `drill`**: the copies in `drill-plan` and `drill-teardown` were deleted on 2026-11-18. `restore-drill.yml` (drill environment) still uses it. `rollback.yml` is an apply through `terraform.yml` and reads the same secrets as a release.

## 3. Branch protection on `main` (Settings > Branches / Rules)

- [ ] Require a pull request before merging; dismiss stale approvals; no bypass for admins (so break-glass changes also land via PR afterwards).
- [ ] Require status checks, branch up to date: `ci`, **`drill-gate`** (commit status posted by `drill.yml` mode=gate on the exact head SHA, T-D98; add it by name once it has been posted at least once), `fmt + validate + lint` and `plan (drill)` / `plan (prod)` from the Terraform workflow, `uv lock --check`.
- [ ] "Require branches to be up to date before merging" is optional: `drill-gate` is already tied to the head SHA, so a new push (including merging `main` into the branch) needs a fresh gate run anyway.
- [ ] Require linked conversation resolution; block force pushes and deletions.
- [ ] Restrict who can push to matching branches (operator only).

## 3b. Tag ruleset on `v*` (ADR-0109)

- [x] Settings > Rules > Rulesets > New tag ruleset: target tags matching `v*`, enforcement Active.
- [x] Restrict creations: only the operator (repository admin role or the operator's bypass entry). Nobody else can mint a release tag.
- [x] Restrict deletions and restrict updates (block force pushes): tags are immutable. A wrong release is superseded by a new version.
- [x] Do not add the GitHub Actions app to the bypass list.
- **Done when:** a non-operator `git push origin v9.9.9` is rejected and `git push --delete origin <existing v* tag>` is rejected for everyone.
- Done 2026-11-16 via the API as two rulesets, because one bypass list covers every rule in a ruleset: `release-tags-create` (creation; bypass: repository admin role) and `release-tags-immutable` (update, deletion, non-fast-forward; no bypass).

## 4. Tailscale OAuth client (admin console > Settings > OAuth clients)

Three OAuth clients. `budget-planner-automation` is used by every environment; `budget-planner-drill-cleanup` only by the drill environments (it deletes the drill's leftover tailnet node after destroy); `budget-planner-prod-cleanup` only by `prod-tailnet` (it deletes the old prod node after a VM replacement):

| Client | Scope | Tag assigned to the client | Goes to |
|---|---|---|---|
| `budget-planner-automation` | `auth_keys` write | `tag:automation` | `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` in `prod`, `prod-plan`, `drill`, `drill-teardown`, `drill-plan` |
| `budget-planner-drill-cleanup` (T-D124) | `devices:core` write | `tag:drill` only | `TS_CLEANUP_CLIENT_ID` / `TS_CLEANUP_SECRET` in `drill-teardown` (used by the reusable `tailnet-cleanup.yml` (T-D133) called from `drill.yml`, `drill-destroy.yml`, `drill-sweeper.yml`, `restore-drill.yml`; formerly the `tailnet-cleanup` jobs of `drill.yml`, `drill-destroy.yml`, `drill-sweeper.yml`) and `drill` (keep in sync) |
| `budget-planner-prod-cleanup` (T-D155; created 2026-11-18) | `devices:core` write | `tag:prod` only | `TS_CLEANUP_CLIENT_ID` / `TS_CLEANUP_SECRET` in `prod-tailnet` only (reusable `tailnet-cleanup.yml` with `env: prod`, called by `release.yml` after a VM replacement) |

- The client is assigned only `tag:automation` (not the machine tags directly). In the ACL (`tailscale-acl.hujson`), `tagOwners` lists `tag:automation` as owner of `tag:prod`, `tag:drill` and `tag:ci`; that is what lets the client mint auth keys for those tags (Terraform `tailscale_tailnet_key`, the workflows' `tailscale/github-action` with `tags: tag:ci`).
- Rotate yearly; see [`tailscale-ssh.md`](tailscale-ssh.md).

### Tailscale admin console prerequisites for the tailnet-only drill (ADR-0101)

- [ ] **DNS > MagicDNS**: enabled.
- [ ] **DNS > HTTPS Certificates**: enabled (Caddy on the drill gets its `*.ts.net` certificate from tailscaled; without this the TLS handshake fails).
- [ ] ACL (`tailscale-acl.hujson`): grant `tag:ci -> tag:drill:443` (the smoke test and `restore-drill.yml` probe `/ready`) in addition to the existing SSH rules. Operators' own devices need `443` to `tag:drill` to browse the drill UI.
- [ ] Copy the tailnet DNS name (e.g. `tail1234.ts.net`) into the `TAILNET_DNS_NAME` variable of `drill`, `drill-teardown` and `drill-plan`.

## 5. Actions settings (Settings > Actions > General)

- [ ] Workflow permissions: read repository contents by default; "Allow GitHub Actions to create and approve pull requests" off.
- [ ] Allow actions: "Allow selected actions"; require full-length commit SHA pinning if available (all workflows already pin SHAs).
- [ ] Fork pull request workflows: require approval for all outside collaborators; do not send secrets to fork PRs.

## Record

| Date | Operator | Notes |
|---|---|---|
| (fill in) | | |
