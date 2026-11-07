# Runbook: GitHub settings checklist (manual, ADR-0099 / ADR-0100)

**Context.** These settings turn "prod only from main via Actions" into something the platform enforces. They cannot be set from Terraform in this repo; re-check them after any repo transfer and at each key rotation. Tick each box once, record the date at the bottom.

## 1. Environments (Settings > Environments)

- [ ] **`prod`**: Required reviewers = you (and prevent self-review only if a second reviewer exists). Deployment branches and tags: **Selected branches: `main` only**. Used by `deploy-prod`, `apply-prod`, `rollback` (env prod).
- [ ] **`prod-plan`** (ungated, used by PR plan leg and `key-expiry.yml`): no reviewers; deployment branches: all branches. It must hold only the **read-only** `ci-plan` key (ADR-0100). Never put write credentials or Litestream/age identities that decrypt prod data here beyond what the plan needs.
- [ ] **`drill`**: no required reviewers. Deployment branches: selected `main` and `*-deploy` (add a pattern per deploy branch convention); allow PR refs only if PR-time drill checks (T-D90) need it, in which case treat the drill environment as untrusted-reachable (it only holds the drill key).
- [ ] Delete **repo-level** `SCW_ACCESS_KEY`, `SCW_SECRET_KEY` (and any repo-level copy of the env secrets below) so a missing environment secret fails instead of falling back.

## 2. Secrets and variables per environment

Same names in every environment, different values (ADR-0093). Verified against `.github/workflows/*.yml`.

| Secret | `prod` | `prod-plan` | `drill` | Notes |
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

## 4. Tailscale OAuth clients (admin console > Settings > OAuth clients)

Two separate clients so a leaked drill secret cannot mint prod-tagged keys:

| Client | Scope | Allowed tags | Goes to |
|---|---|---|---|
| `budget-planner-prod` | `auth_keys` write | `tag:prod`, `tag:ci` | `prod` and `prod-plan` env: `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` |
| `budget-planner-drill` | `auth_keys` write | `tag:drill`, `tag:ci` | `drill` env: same secret names |

- `tag:ci` is needed in both because the deploy workflows join the tailnet as `tag:ci` using the same secret names (limitation: the tag cannot be split without renaming secrets in the workflows; tracked as follow-up).
- Tag owners (`tagOwners`) in the ACL must allow the OAuth client to own each tag (`tailscale-acl.hujson`).
- Rotate yearly; see [`tailscale-ssh.md`](tailscale-ssh.md).

## 5. Actions settings (Settings > Actions > General)

- [ ] Workflow permissions: read repository contents by default; "Allow GitHub Actions to create and approve pull requests" off.
- [ ] Allow actions: "Allow selected actions"; require full-length commit SHA pinning if available (all workflows already pin SHAs).
- [ ] Fork pull request workflows: require approval for all outside collaborators; do not send secrets to fork PRs.

## Record

| Date | Operator | Notes |
|---|---|---|
| (fill in) | | |
