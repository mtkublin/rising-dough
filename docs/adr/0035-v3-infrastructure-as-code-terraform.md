# ADR-0035: v3 Infrastructure as Code — Terraform (Scaleway Provider) + Cloud-Init Bootstrap

- **Status**: Proposed
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28)
- **Amended by**: [ADR-0096](0096-terraform-state-bootstrap-stack.md) (§4 bootstrap)
- **Related**: ADR-0032 (v3 remote deployment), ADR-0034 (Litestream), ADR-0036 (Caddy TLS), ADR-0037 (GHA deploy pipeline)

## Context

Everything that touches Scaleway must be declarable, reviewable, and reproducible. The user explicitly specified **Terraform** (not OpenTofu) for Scaleway resources in this session.

Decision drivers:

- Full tear-down + re-provision must be a single command for disaster recovery (RTO target < 60 min from ADR-0032).
- Secrets (Scaleway API keys, IAM credentials, the fallback password hash) must stay outside git.
- The remote state must be hosted on infrastructure the deployment itself does not depend on (so a destroyed project can still be restored).
- Scaleway's official Terraform provider is actively maintained and covers Instances, Object Storage, DNS, IAM.

## Decision

### 1. Tooling

- **Terraform** v1.9+ (official HashiCorp build; CI pins the exact version via a `.terraform-version` file consumed by `hashicorp/setup-terraform@v3`).
- **Scaleway provider**: `scaleway/scaleway`, version pinned in `terraform/versions.tf` (first implementation pins the latest stable at Phase 2 start).
- No OpenTofu, no Pulumi, no Ansible. Cloud-init handles in-VM configuration directly (see §5).

### 2. Repository layout

```
terraform/
├── versions.tf           # terraform + required_providers block
├── providers.tf          # scaleway provider configuration
├── variables.tf          # input variables + validation
├── backend.tf            # S3-compatible remote state on Scaleway Object Storage
├── main.tf               # top-level composition
├── modules/
│   ├── compute/          # scaleway_instance + flex IPv4 + security group + cloud-init render
│   ├── storage/          # scaleway_object_bucket (durability bucket for Litestream)
│   ├── iam/              # scaleway_iam_application + policy + API key
│   └── dns/              # scaleway_domain_record (A + AAAA)
├── cloud-init/
│   ├── bootstrap.yaml.tpl        # cloud-init user-data template
│   └── compose/
│       ├── docker-compose.yml.tpl
│       ├── Caddyfile.tpl
│       └── litestream.yml.tpl
├── envs/
│   ├── prod/
│   │   ├── terraform.tfvars      # non-secret variables for prod
│   │   └── backend.hcl           # backend config
│   └── drill/
│       ├── terraform.tfvars
│       └── backend.hcl
└── README.md             # bootstrap, apply, destroy, drill procedure
```

### 3. Managed resources

| Resource | Terraform type | Notes |
|---|---|---|
| Scaleway project | `scaleway_account_project` | One per environment (`prod`, `drill`). Shared account; isolated project per env. |
| IAM application | `scaleway_iam_application` | Non-human identity for cloud-init + Litestream. |
| IAM policy | `scaleway_iam_policy` | Least-privilege: `ObjectStorageFullAccess` scoped to the project. |
| IAM API key | `scaleway_iam_api_key` | Written as a sensitive output; piped into cloud-init only. |
| Object storage bucket (durability) | `scaleway_object_bucket` | `pl-waw`, versioning on, no public access, SSE on. |
| Object storage bucket (TF state) | `scaleway_object_bucket` | `budget-planner-tfstate-pl-waw`. Created out-of-band once, bootstrap script in `terraform/README.md`. |
| Instance | `scaleway_instance_server` | Stardust1-S, Ubuntu 24.04. `user_data` from `cloud-init/bootstrap.yaml.tpl`. |
| Flex IP | `scaleway_instance_ip` | IPv4 attached to the instance. |
| Security group | `scaleway_instance_security_group` | Inbound allow: `80/tcp`, `443/tcp`, `443/udp`; `22/tcp` removed by ADR-0094 (SSH over Tailscale). Outbound: unrestricted (Litestream + ACME + GHCR). |
| DNS zone | `scaleway_domain_zone` | If the hostname is on a Scaleway-managed domain. Otherwise external DNS → documented out-of-band. |
| DNS A/AAAA records | `scaleway_domain_record` | Points `budget.<domain>` at the instance IPs. |
| Instance snapshot schedule | *out of scope v3* | Defence-in-depth; a cron on the host emits `scw` CLI calls, documented in the runbook. |

### 4. Remote state

- Backend: **S3-compatible** on Scaleway Object Storage (`budget-planner-tfstate-pl-waw`).
- State locking: provider `use_lockfile = true` (Terraform v1.10+ native state locking against S3-compatible stores) once the implementation phase confirms the provider version supports it. If not, a DynamoDB-compatible lock is left as a known gap and the user is the sole operator (one-writer invariant).
- `backend.tf` is empty; backend config is passed per environment via `terraform init -backend-config=envs/<env>/backend.hcl`.
- **Amended by [ADR-0096](0096-terraform-state-bootstrap-stack.md) (2026-11-06): the bootstrap bucket is now created by the separate Terraform root stack `terraform/bootstrap/` (local state); the script below was removed.**
- (Historical) The bootstrap bucket was created by a one-shot script (`terraform/scripts/bootstrap-state.sh`) that runs `scw object bucket create` using the operator's personal API key *before* `terraform init`. This is the only non-Terraform step and is documented in `terraform/README.md`.

### 5. In-VM configuration (cloud-init)

The instance is provisioned with `user_data` templated by Terraform. The template includes:

1. Package install: `docker.io`, `docker-compose-plugin`, `ufw`, `fail2ban`, `unattended-upgrades`.
2. User creation: `app` user, no sudo, no password, SSH key in `authorized_keys` restricted to the deploy command (ADR-0037).
3. Directory layout: `/data` (mode 0700, uid=app), `/etc/budget-planner/` (mode 0700, root).
4. Rendered templates landed on disk:
   - `/etc/budget-planner/docker-compose.yml` (template inputs: image tag, hostname).
   - `/etc/budget-planner/Caddyfile` (template inputs: hostname).
   - `/etc/budget-planner/litestream.yml` (template inputs: bucket name).
   - `/etc/budget-planner/litestream.env` — IAM credentials, mode 0600, root.
5. Firewall: `ufw default deny incoming`, allow 22/80/443 (22 is gated by the security group, ADR-0094), enable.
6. `fail2ban` jails: `sshd`, `caddy-auth` (reads Caddy access log for repeated 401s on `/auth/*`).
7. Unattended-upgrades: security pocket enabled; auto-reboot at 04:00 Europe/Warsaw with a `pre-reboot` hook that `docker compose stop app` → waits 15 s for Litestream flush → `shutdown -r now`.
8. First-boot pull: `docker login ghcr.io` using a deploy-only PAT (surfaced into cloud-init), `docker compose pull && docker compose up -d`.
9. Health probe: cloud-init waits for `curl -fsS https://localhost/health` through Caddy before marking the instance as ready.

Cloud-init logs land in `/var/log/cloud-init-output.log` on the VM; a successful bootstrap is a required Phase 2 acceptance signal.

### 6. Secrets and sensitive outputs

- Scaleway API key (operator) stays in the operator's shell (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`) and is never committed. CI uses a GitHub Actions encrypted secret.
- The IAM API key for Litestream is created by Terraform (`sensitive = true` output) and read by cloud-init via Terraform templating. It never leaves the state file; `terraform.tfstate` lives in the private state bucket.
- The fallback password hash from ADR-0033 is generated by `random_password` (sensitive), hashed with bcrypt by a `null_resource` running a one-shot container, and written to the DB via a cloud-init migration. Plaintext is a single `terraform output -raw admin_fallback_password` for the operator to capture into their password manager.
- Rotation: `terraform apply -replace='random_password.admin_fallback'` + re-apply.

### 7. Environments

- `prod` — the real deployment.
- `drill` — a disposable environment used by the monthly restore drill (ADR-0034 §5) and by the Phase 4 acceptance drill. Reads from the prod bucket with a **read-only** IAM credential; writes to a separate `budget-planner-drill-pl-waw` scratch bucket. `drill` is torn down after each exercise.

### 8. CI / review

- Terraform plan runs on PR via `hashicorp/setup-terraform@v3` + `terraform plan -input=false -lock=false`. Plan output posted as a PR comment.
- Terraform apply runs only on push to `main` after CI is green **and** the human operator approves the GitHub Actions environment "prod". No apply-on-PR, no auto-apply.
- `terraform fmt -check` + `terraform validate` + `tflint` + `tfsec` gate every PR.

## Consequences

### Positive

- One command (`terraform apply`) rebuilds the entire deployment. One command (`terraform destroy`) tears it down for cost-saving or disaster testing.
- Secret surface is minimal and auditable. Only the operator's personal Scaleway API key is handled outside Terraform.
- The drill environment is a real test of the same Terraform code, not a parallel codebase.

### Negative

- First-time setup requires a one-shot `scw` CLI run to create the state bucket (chicken-and-egg). Documented explicitly in `terraform/README.md`.
- Scaleway's Terraform provider is less battle-tested than AWS's. Non-fatal bugs may surface and need version pinning / workarounds. The project pins the provider version aggressively and reads release notes before upgrades.
- Cloud-init templates are not type-checked. Rendering errors surface at `terraform apply` time, not plan time. Mitigation: `terraform validate` + a `yq -e .` + `caddy validate --config -` smoke test on the rendered templates in CI.

### Follow-ups

- Future ADR: migrate to a per-environment Terraform Cloud workspace if a second operator is ever added (not needed for the single-user case).
- Future ADR: add a cross-region replica of the state bucket if the primary region ever experiences a long outage.

## Alternatives Considered

- **OpenTofu** — explicitly ruled out by the user for this project.
- **Pulumi (Python)** — attractive given the project is Python-first; rejected because Terraform's Scaleway provider has more coverage and the ecosystem (`tflint`, `tfsec`, `atlantis`) is more mature.
- **Ansible-only** — rejected; good at config, bad at life-cycle of cloud resources (IAM, DNS, buckets).
- **Scaleway Console (click-ops)** — rejected; violates reproducibility and auditability goals.
