# Phase 2 — Infrastructure (Terraform + cloud-init)

All Scaleway resources are managed by **Terraform** (ADR-0035). Sequential within the phase; see `../implementation_plan.md` for the exact order.

Full task shape lives in `../tasks.md`. Detailed task files are added here as each task is picked up.

- [T-D20](T-D20-tf-bootstrap.md) — Terraform bootstrap (state bucket, versions, providers).
- T-D21 — IAM + Object Storage modules. See `../tasks.md` for details.
- T-D22 — DNS module.
- [T-D23](T-D23-cloud-init.md) — Cloud-init templates (the complex one; detailed here).
- T-D24 — Compute module.
- [T-D25](T-D25-first-apply-drill.md) — First drill apply (detailed here; the local-apply steps are superseded by `drill.yml`, ADR-0099).
- T-D26 — Teardown drill.
- T-D27 — First apply on `prod`.
- T-D28 — Terraform CI (plan on PR, apply on main w/ approval).
