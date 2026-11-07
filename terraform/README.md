# Terraform — budget-planner (v3)

Scaleway infrastructure as code for the v3 remote deployment. Authoritative references:

- [ADR-0032](../docs/adr/0032-v3-remote-deployment-scaleway-stardust-warsaw.md) — compute + storage topology.
- [ADR-0034](../docs/adr/0034-v3-sqlite-replication-litestream.md) — Litestream durability.
- [ADR-0035](../docs/adr/0035-v3-infrastructure-as-code-terraform.md) — this module layout + state backend.
- [ADR-0036](../docs/adr/0036-v3-reverse-proxy-caddy-auto-tls.md) — Caddy TLS termination.
- [ADR-0061](../docs/adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §3 — admin bootstrap flow.

## Layout

```text
terraform/
├── versions.tf              # terraform >= 1.10, scaleway + random providers
├── providers.tf             # provider wiring (region/zone from vars)
├── backend.tf               # empty S3-compatible backend block; config via envs/<env>/backend.hcl
├── variables.tf             # operator inputs + computed locals
├── main.tf                  # top-level composition (random secrets + module wiring)
├── outputs.tf               # sensitive outputs (admin_initial_password, scw_* keys, cookie_secret)
├── envs/
│   ├── drill/{backend.hcl, terraform.tfvars.example}
│   └── prod/{backend.hcl, terraform.tfvars.example}
├── modules/
│   ├── iam/      # application + policy + API key
│   ├── storage/  # durability bucket (versioning on, SSE, no public, 30d lifecycle)
│   ├── dns/      # A/AAAA records only; zone is never owned by Terraform (ADR-0088)
│   └── compute/  # Stardust1-S + Flex IPv4 + security group + user_data
├── cloud-init/
│   ├── bootstrap.yaml.tpl           # first-boot sequence
│   ├── compose/
│   │   ├── docker-compose.yml.tpl   # app + litestream + caddy
│   │   ├── Caddyfile.tpl            # auto-TLS, CSP nonce, access log
│   │   └── litestream.yml.tpl       # WAL replication to Scaleway Object Storage
│   └── bin/deploy-budget-planner.tpl # restricted deploy command (T-D32 finalises)
├── bootstrap/                       # state-bucket root stack, local state (ADR-0096)
└── scripts/
```

## One-time state bootstrap (ADR-0035 §4)

Terraform cannot store its own state in a bucket that does not exist yet. The bucket is created once by the separate root stack in [`bootstrap/`](bootstrap/README.md) (local state, committed after the first apply; ADR-0096, which replaced `scripts/bootstrap-state.sh`).

```sh
cd terraform/bootstrap
set -a; source ../.env; set +a
export TF_VAR_scaleway_project_id=... TF_VAR_scaleway_organization_id=...
terraform init && terraform plan && terraform apply
```

The stack creates `budget-planner-tfstate-pl-waw` in `pl-waw`, versioned and private. Re-run `terraform plan` later only to check drift.

## Per-environment apply

Two environments share the same code: `drill` (disposable) and `prod`. State is split by `key` in each `backend.hcl` so one apply never collides with the other.

```sh
cd terraform
cp envs/drill/terraform.tfvars.example envs/drill/terraform.tfvars  # gitignored; fill real values
export SCW_ACCESS_KEY=...
export SCW_SECRET_KEY=...
export TF_VAR_ghcr_pull_pat=ghp_...                                 # read-only GHCR PAT

terraform init -backend-config=envs/drill/backend.hcl -reconfigure
terraform validate
terraform plan  -var-file=envs/drill/terraform.tfvars
# No local drill apply: dispatch drill.yml instead (ADR-0099, runbooks/drill.md).
```

CI (`terraform.yml`, `restore-drill.yml`) never uses a tfvars file: every input is a `TF_VAR_<name>` env var from GitHub secrets, scoped by the `drill` / `prod` / `prod-plan` environments (ADR-0093; secret table in `docs/plans/v3/operator-checklist.md` A5). `scripts/check_tf_vars.py` fails fast on any empty required input. List inputs are passed as HCL/JSON strings, e.g. `TF_VAR_bucket_admin_principals='["user_id:<uuid>"]'`.

For `prod`, do not apply from a laptop: per [ADR-0099](../docs/adr/0099-release-and-environment-policy.md) prod is applied only by GitHub Actions from `main` (environment `prod`, reviewer approval). The only exceptions are the 2026-11-07 initial bring-up, the bootstrap stack and the break-glass runbook. The pipelines landed with T-D89 (release) and T-D90 (drill). Locally, use the drill commands above for `plan` only; drill applies go through `drill.yml`.

## Preflight (T-D78)

Before any apply, run `just drill-preflight` (or `just tf-preflight prod`). It is read-only, takes seconds, sources `terraform/.env` if present, and prints PASS or FAIL per check without ever printing a secret value (lengths and prefix status only). Exit code is non-zero if anything fails.

| Check | Catches |
|---|---|
| Required inputs (`SCW_*`, Tailscale OAuth, age identity/recipient, GHCR PAT) | empty, `<placeholder>` or wrong-prefix values |
| Project match | `SCW_DEFAULT_PROJECT_ID` differing from `scaleway_project_id` (the provider silently uses the env value). The drill recipe maps `SCW_DRILL_PROJECT_ID` onto it |
| App image on GHCR | `ghcr.io/<github_owner>/budget-planner:<app_image_tag>` not published (`NAME_UNKNOWN`) |
| Tailscale tag | OAuth client cannot mint a key for `tag:drill` / `tag:prod`; mints a 300 s ephemeral key and deletes it at once |
| State backend | bucket from `backend.hcl` unreachable with the SCW keys (stdlib SigV4 `HEAD`, no extra dependency) |

It does not run `terraform fmt -check` or `validate`; run those separately (T-D77 `tf-render-check` when present).

## Secret flow

| Secret | Source | Sink |
|---|---|---|
| Operator Scaleway API key | Operator shell (`SCW_ACCESS_KEY` / `SCW_SECRET_KEY`) | Terraform CLI only. Never written to state. |
| IAM app access/secret key | Generated by `module.iam.scaleway_iam_api_key.app` | Rendered into `/etc/budget-planner/litestream.env` + compose env via cloud-init. |
| Prod replica read-only key (drill only) | Created by prod state (`module.restore_reader`, outputs `restore_reader_access_key` / `_secret_key`, ADR-0092); stored as `drill`-env secrets `PROD_REPLICA_RO_*`, passed as `TF_VAR_scw_access_key_restore` / `TF_VAR_scw_secret_key_restore` | `/etc/budget-planner/restore-source.env` (0600) on the drill VM, used by `restore-from-prod` (T-D41a). |
| GHCR pull PAT | Operator-supplied `TF_VAR_ghcr_pull_pat` (CI: secret `GHCR_PULL_PAT`) | Rendered into `/root/.docker/config.json` on the VM. |
| Admin initial password | `random_password.admin_initial_password` | Compose env `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`. Capture once from `terraform output -raw admin_initial_password`. |
| Session cookie signing secret | `random_password.cookie_secret` | Compose env `BUDGET_COOKIE_SECRET`. |

Rotation (prod changes are break-glass only, ADR-0099; drill: re-dispatch `drill.yml`):

- Admin password: break-glass `terraform apply -replace='random_password.admin_initial_password'`. The env var is **not** reconciled continuously — the on-host app only consumes it on first-boot bootstrap. To rotate an existing admin, use `/settings/password` as that admin, or `/settings/users/<id>/reset-password` as another admin (ADR-0061 §4).
- Scaleway IAM key: break-glass `terraform apply -replace='module.iam.scaleway_iam_api_key.app'`.
- Cookie secret: break-glass `terraform apply -replace='random_password.cookie_secret'`.

## Destroy

```sh
# Routine drill teardown: `gh workflow run drill-destroy.yml` (ADR-0099). The local form is break-glass only.
terraform destroy -var-file=envs/drill/terraform.tfvars
```

The durability bucket's lifecycle rule (7-day noncurrent expiry, derived from `backup_max_age_days = 37` minus the 30-day Litestream retention; T-D57) reclaims noncurrent versions; the bucket itself is destroyed in-place. Caddy's `/data` volume is destroyed with the VM.

## Validation hooks

Run before pushing a Terraform change:

```sh
terraform fmt -recursive
terraform fmt -check -recursive
terraform validate                                   # requires `init`
# Optional, if installed locally:
tflint --recursive
trivy config terraform/ || tfsec terraform/
```

CI replays the same gates on every PR via `.github/workflows/terraform.yml` and additionally renders the cloud-init templates to check they parse as valid YAML / Caddyfile / Litestream TOML.

## Offline user-data render check (T-D77)

Catches first-boot config bugs (e.g. `#cloud-config` not on line 1, T-D75) without paying for a VM boot. `tests/render/` is a fixture root that calls the real `modules/compute` (same `templatefile()` chain as the server) with obviously fake values; no credentials, no API calls (dummy provider config only; just provider downloads).

```sh
just tf-render-check
# = terraform -chdir=terraform init -backend=false && terraform -chdir=terraform test
#   + python3 terraform/tests/render/render_check.py
```

- `terraform test` (`tests/render.tftest.hcl`, mocked scaleway provider) asserts line 1 is `#cloud-config`, with and without the drill restore helper.
- `render_check.py` plans the fixture, extracts the rendered user-data, and checks line 1, YAML parsing, and `cloud-init schema --config-file`. Locally the schema step is skipped with a message when `cloud-init` is not installed; CI installs it and passes `--require-schema`.
- `--out DIR` keeps the rendered files (dummy secrets only).

## Known limitations

- `scaleway/scaleway` provider lags AWS in object-bucket primitives. Public-access blocking is enforced via a deny-plaintext bucket policy; the per-bucket encryption toggle is enforced by Scaleway at the account level.
- `use_lockfile = true` in `backend.hcl` requires Terraform 1.10+ for native S3 lockfile support. The floor is `>= 1.10.0` (`versions.tf`, ADR-0090). CI and `.terraform-version` pin Terraform `1.17.1`.
- The `deploy-budget-planner` script shipped here is a stub; T-D32 finalises the exact rollback catalog once the compose template stabilises in production.

## Projects (ADR-0092)

Each env lives in its own Scaleway project via `scaleway_project_id` (drill: `rising-dough-drill`, prod: `rising-dough`). DNS records of both envs are created in the zone's project (`dns_zone_project_id`, default = prod project). Prod also owns the stable read-only `restore-reader` IAM application used by the restore drill, so apply prod before the first automated drill.
