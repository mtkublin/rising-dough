# Runbook: GitHub settings checklist (manual, ADR-0099 / ADR-0100)

**Context.** These settings turn "prod only from main via Actions" into something the platform enforces. They cannot be set from Terraform in this repo; re-check them after any repo transfer and at each key rotation. Tick each box once, record the date at the bottom.

## 1. Environments (Settings > Environments)

- [ ] **`prod`**: Required reviewers = you (and prevent self-review only if a second reviewer exists). Deployment branches and tags: **Selected branches: `main` only**. Used by `deploy-prod`, `apply-prod`, `rollback` (env prod).
- [ ] **`prod-plan`** (ungated, used by PR plan leg and `key-expiry.yml`): no reviewers; deployment branches: all branches. It must hold only the **read-only** `ci-plan` key (ADR-0100). Never put write credentials or Litestream/age identities that decrypt prod data here beyond what the plan needs.
- [ ] **`drill`** (gated, ADR-0101): **Required reviewers** = you (every drill apply, from any trigger: `*-deploy` push, dispatch, PR pre-merge, waits for approval; prevent self-review only if a second reviewer exists). Deployment branches and tags: selected `main` and `*-deploy` (plus PR refs only if the pre-merge drill check must run for PRs from branches that are not `*-deploy`; the approval is then what stops unreviewed code). Used only by the `apply` job of `terraform.yml` for drill and by `restore-drill.yml`.
- [ ] **`drill-teardown`** (ungated, ADR-0101): no reviewers; deployment branches: all branches. Used by every drill destroy path (`drill-sweeper.yml` scan + destroy, `drill-destroy.yml`, the `teardown` job of `drill.yml`) and by the drill `smoke` job, so teardown never waits for approval. Holds the same drill secrets and variables as `drill` (section 2).
- [ ] **`drill-plan`** (ungated, ADR-0101): no reviewers; deployment branches: all branches. Used by the drill leg of the PR plan in `terraform.yml` (mirrors `prod-plan`). Same drill secrets as `drill`.
- Private repositories: **Required reviewers on environments need GitHub Pro/Team** (or an org plan). On the free plan the setting is unavailable and the drill apply is NOT gated; do not rely on this checklist until the plan supports it.
- A drill run waiting for approval holds the `drill` concurrency group, so the sweeper and `drill-destroy.yml` queue behind it. Approve or reject/cancel pending drill runs promptly.
- [ ] Delete **repo-level** `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` (and any repo-level copy of the env secrets below) so a missing environment secret fails instead of falling back.

## 2. Secrets and variables per environment

Same names in every environment, different values (ADR-0093). The three drill environments (`drill`, `drill-teardown`, `drill-plan`) hold identical copies of the drill column; keep them in sync when rotating (`key-rotation.md`). Verified against `.github/workflows/*.yml`.

| Secret | `prod` | `prod-plan` | `drill`, `drill-teardown`, `drill-plan` | Notes |
|---|:-:|:-:|:-:|---|
| `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` | ci-prod | ci-plan (read-only) | ci-drill | outputs of `terraform/bootstrap/ci` |
| `SCW_DEFAULT_PROJECT_ID` | prod project | prod project | drill project | |
| `SCW_DEFAULT_ORG_ID` | x | x | x | also used by `key-expiry.yml` (prod-plan) |
| `ADMIN_EMAIL`, `APP_DOMAIN` | x | x | x | |
| `OPERATOR_SSH_PUBKEY`, `GITHUB_DEPLOY_PUBKEY` | x | x | x | |
| `GHCR_PULL_PAT` | x | x | x | read:packages only |
| `LITESTREAM_AGE_IDENTITY`, `LITESTREAM_AGE_RECIPIENT` | x | x | x | per-env age keypair |
| `MANAGED_DNS_ZONE` (optional) | x | x | x | |
| `BUCKET_ADMIN_PRINCIPALS`, `BUCKET_READONLY_PRINCIPALS` (optional) | x | x | x | |
| `PROD_REPLICA_RO_ACCESS_KEY`, `PROD_REPLICA_RO_SECRET_KEY` | | | x | restore-reader of prod replica; drill only |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | prod client | prod client (plan reads only) | drill client | see section 4 |
| `DEPLOY_SSH_PRIVATE_KEY` | x | | x | different key per env |
| `DEPLOY_SSH_KNOWN_HOSTS` | x | | x | |
| `DEPLOY_SSH_KNOWN_HOSTS_DRILL` | | | x | restore-drill |
| `PROD_HOST` | x | | | tailnet name, e.g. `budget-planner-prod` |
| `DRILL_HOST` | | | x | e.g. `budget-planner-drill` |

| Variable | `prod` | `drill` |
|---|:-:|:-:|
| `PROD_URL` | x | |
| `DRILL_URL` | | x |

Repo-level (not environment): `CODEQL_TOKEN` (security.yml). `GITHUB_TOKEN` is automatic.

Note: `rollback.yml` selects the environment from its `env` input, so it reads `PROD_HOST`/`DRILL_HOST`/`*_URL` from the chosen environment; make sure both host secrets resolve where used (if a workflow reads a secret from an environment that does not hold it, add it there).

## 3. Branch protection on `main` (Settings > Branches / Rules)

- [ ] Require a pull request before merging; dismiss stale approvals; no bypass for admins (so break-glass changes also land via PR afterwards).
- [ ] Require status checks, branch up to date: `ci`, the pre-merge drill check (T-D90), `fmt + validate + lint` and `plan (drill)` / `plan (prod)` from the Terraform workflow, `uv lock --check`.
- [ ] Require linked conversation resolution; block force pushes and deletions.
- [ ] Restrict who can push to matching branches (operator only).

## 4. Tailscale OAuth client (admin console > Settings > OAuth clients)

One OAuth client, used by every environment:

| Client | Scope | Tag assigned to the client | Goes to |
|---|---|---|---|
| `budget-planner-automation` | `auth_keys` write | `tag:automation` | `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` in `prod`, `prod-plan`, `drill`, `drill-teardown`, `drill-plan` |

- The client is assigned only `tag:automation` (not the machine tags directly). In the ACL (`tailscale-acl.hujson`), `tagOwners` lists `tag:automation` as owner of `tag:prod`, `tag:drill` and `tag:ci`; that is what lets the client mint auth keys for those tags (Terraform `tailscale_tailnet_key`, the workflows' `tailscale/github-action` with `tags: tag:ci`).
- Rotate yearly; see [`tailscale-ssh.md`](tailscale-ssh.md).

## 5. Actions settings (Settings > Actions > General)

- [ ] Workflow permissions: read repository contents by default; "Allow GitHub Actions to create and approve pull requests" off.
- [ ] Allow actions: "Allow selected actions"; require full-length commit SHA pinning if available (all workflows already pin SHAs).
- [ ] Fork pull request workflows: require approval for all outside collaborators; do not send secrets to fork PRs.

## Record

| Date | Operator | Notes |
|---|---|---|
| (fill in) | | |
