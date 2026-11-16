# T-D61 — Data inventory + "what the operator can see in v3"

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: no (documents the end state of T-D54..T-D60)
- **Depends on**: T-D54..T-D60
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §8, [ADR-0079](../../../adr/0079-v4-threat-model-and-data-protection-goals.md)

## Context

No written inventory exists of where user data and secrets live, and users have not been told what the operator can technically see. v4 needs this as its baseline.

## Deliverables

1. `docs/plans/v3/runbooks/data-inventory.md` with a table per location: live DB + WAL (`/data/budget.db*`), Litestream bucket (age-encrypted after T-D56), pre-migration backups, drill host, app logs (stdout → Docker json-file; rotation config), Caddy access log, Terraform state bucket (secrets, no user data), cloud-init user-data (secrets), GitHub secrets, browser (after T-D55). Columns: what, who can read, protection, retention, erasure method.
2. Section **"What the operator can technically see in v3"** — plain language, honest: with host access the operator can read all user data; backups require host access or the age identity; admin UI shows no user data (after T-D54). Points to v4 plan.
3. Link from `runbooks/user-admin.md` and `docs/plans/v3/README.md`.

## Acceptance criteria

- Every row cites the task/ADR that sets its protection and retention.
- Operator reviewed and ticked the item in `operator-checklist.md`.

## Validation hook

Docs-only. `just lint` (markdown links) green.
