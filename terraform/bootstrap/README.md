# Terraform state bootstrap stack

Creates the remote-state bucket (`budget-planner-tfstate-pl-waw`, `pl-waw`) that the main stack in `../` uses as its backend. ADR-0096 (amends ADR-0035 section 4); replaces the former `scripts/bootstrap-state.sh`.

This stack uses the **local backend**. Its `terraform.tfstate` holds only bucket metadata (no secrets) and is committed to git after the first apply (`../.gitignore` has a negation for that one path).

## Operator steps (once)

```sh
cd terraform/bootstrap
set -a; source ../.env; set +a        # SCW_ACCESS_KEY / SCW_SECRET_KEY (operator key)
export TF_VAR_scaleway_project_id=...
export TF_VAR_scaleway_organization_id=...
terraform init
terraform plan
terraform apply
git add terraform.tfstate && git commit -m "chore(T-D72): bootstrap state"
```

2026-11-06: first apply done by the operator; state committed (T-D72b).

The stack is applied once. Afterwards re-run `terraform plan` only to check drift. `prevent_destroy` and `force_destroy = false` guard the bucket; there is intentionally no bucket policy (ADR-0096).
