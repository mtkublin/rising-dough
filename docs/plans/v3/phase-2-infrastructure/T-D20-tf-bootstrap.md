# T-D20 — Terraform bootstrap (state bucket, versions, providers)

- **Phase**: 2 — Infrastructure
- **Sequential**: this is the first infrastructure task; everything else in Phase 2 depends on it
- **Depends on**: nothing (one-shot bootstrap before `terraform init`)
- **Blocks**: T-D21..T-D28
- **References**: ADR-0035 §1, §2, §4

## Context

Terraform cannot store its own state if the state bucket does not exist yet. The project avoids the chicken-and-egg by creating the state bucket out-of-band with a single `scw` CLI call. This is the only non-Terraform step for Scaleway resources.

## Deliverables

1. `terraform/scripts/bootstrap-state.sh` — idempotent script that creates `budget-planner-tfstate-pl-waw` in `pl-waw` with versioning on, no public access. Reads `SCW_ACCESS_KEY` + `SCW_SECRET_KEY` from the operator's environment.
2. `terraform/.terraform-version` — pins Terraform 1.17.1 (raised from 1.9 by T-D64, ADR-0090).
3. `terraform/versions.tf`:
   ```hcl
   terraform {
     required_version = ">= 1.10.0"
     required_providers {
       scaleway = {
         source  = "scaleway/scaleway"
         version = "~> 2.46"   # pin at implementation time to latest stable
       }
       random = {
         source  = "hashicorp/random"
         version = "~> 3.6"
       }
     }
   }
   ```
4. `terraform/providers.tf`:
   ```hcl
   provider "scaleway" {
     project_id = var.scw_project_id
     region     = "pl-waw"
     zone       = "pl-waw-2"  # ADR-0084
   }
   ```
5. `terraform/backend.tf` — empty backend block; config supplied per environment:
   ```hcl
   terraform {
     backend "s3" {}
   }
   ```
6. `terraform/envs/drill/backend.hcl` and `terraform/envs/prod/backend.hcl`:
   ```hcl
   bucket                      = "budget-planner-tfstate-pl-waw"
   key                         = "drill/terraform.tfstate"       # or prod/
   endpoint                    = "https://s3.pl-waw.scw.cloud"
   region                      = "pl-waw"
   skip_credentials_validation = true
   skip_region_validation      = true
   skip_metadata_api_check     = true
   use_lockfile                = true                             # verify provider supports; fall back to one-writer invariant
   ```
7. `terraform/variables.tf` — declare `scw_project_id`, `scw_access_key` (sensitive), `scw_secret_key` (sensitive), `hostname`, `env`.
8. `terraform/README.md`:
   - How to bootstrap the state bucket (one-time).
   - How to `terraform init -backend-config=envs/<env>/backend.hcl`.
   - How to apply + destroy per environment.
   - How to rotate the fallback password (ADR-0033 §2).

## Acceptance criteria

- `terraform fmt -check` passes repo-wide.
- `terraform init -backend-config=envs/drill/backend.hcl` succeeds without errors.
- `terraform validate` succeeds.
- Running `bootstrap-state.sh` twice is idempotent (second run reports "already exists" and exits 0).
- `terraform plan` on an empty composition emits "no changes".

## Validation hook

```sh
cd terraform
export SCW_ACCESS_KEY=...
export SCW_SECRET_KEY=...
./scripts/bootstrap-state.sh         # idempotent
terraform init -backend-config=envs/drill/backend.hcl
terraform validate
terraform plan -var-file=envs/drill/terraform.tfvars
```
