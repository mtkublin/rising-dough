# T-D25 — First `terraform apply` on the `drill` environment

> **Superseded by ADR-0099 (2026-11-07).** The first drill apply is now run by the drill pipeline (`drill.yml`), not a local `terraform apply -var-file=...`. Current procedure: [`runbooks/drill.md`](../runbooks/drill.md). The text below is the original spec, kept as written.

- **Phase**: 2 — Infrastructure
- **Sequential**: last step of Phase 2 (except T-D26 teardown and T-D27 prod)
- **Depends on**: T-D21, T-D22, T-D24 (full module set + cloud-init)
- **References**: ADR-0035

## Context

The first real apply. Everything up to this point has been template work and `terraform plan`. This task validates that the whole plan executes correctly against a disposable environment before anything touches prod.

## Deliverables

- `terraform/envs/drill/terraform.tfvars` filled with real inputs:
  - `scw_project_id`
  - `hostname` = e.g. `drill.budget.<domain>` (operator-owned)
  - any other non-secret variables declared in `variables.tf`
- Documented command sequence:
  ```sh
  cd terraform
  export SCW_ACCESS_KEY=...
  export SCW_SECRET_KEY=...
  terraform init -backend-config=envs/drill/backend.hcl -reconfigure
  terraform apply -var-file=envs/drill/terraform.tfvars
  terraform output -raw admin_fallback_password | pbcopy   # capture to password manager; close terminal
  ```
- Post-apply manual verification (recorded as a dated row in `../runbooks/restore-log.md` once that file exists; otherwise capture in the PR description):
  1. `curl -fsS https://drill.budget.<domain>/health` → 200.
  2. `curl -fsS https://drill.budget.<domain>/ready` → 200 with `"db": "ok"`.
  3. Mozilla Observatory check against the drill hostname → grade ≥ A.
  4. `nslookup drill.budget.<domain>` resolves to the flex IP.
  5. SSH as `operator` works; SSH as `deploy` without a command returns the deploy-script usage line and exits non-zero.
  6. `scw object bucket list` shows `budget-planner-drill-pl-waw`.
  7. Litestream has written a generation within 15 s of the first app write.

## Acceptance criteria

- `terraform apply` completes without manual intervention.
- `terraform plan` immediately after apply emits "no changes".
- All seven post-apply checks pass; results captured in the PR description.
- `terraform output` lists only expected keys; no secret leaks into logs.

## Validation hook

```sh
# After apply:
curl -fsS https://drill.budget.<domain>/health
curl -fsS https://drill.budget.<domain>/ready | jq .
testssl.sh --quiet --fast drill.budget.<domain>
```

Expect: Observatory grade ≥ A, testssl grade A, both health endpoints 200.
