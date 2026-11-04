# Rising Dough v3 — Remote Deployment Work Plan

> v3 scope: take the local app (v1 functional surface + v2 Rising Dough redesign) and put it on the public internet, hosted on **Scaleway Stardust Warsaw** + **Scaleway Object Storage Warsaw** (ADR-0032), with continuous Litestream replication (ADR-0034), per-user password + optional passkey auth (ADR-0033 as amended by ADR-0061), auto-TLS via Caddy (ADR-0036), Terraform-managed infrastructure (ADR-0035), and a GitHub Actions deploy pipeline (ADR-0037). **Multi-user support** is in scope at order-of-magnitude 10 users, admin-managed, with strict per-user data isolation — see [ADR-0061](../../adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md).
>
> **Non-goals**: self-signup, external IdP, admin impersonation, "forgot password" email flow, hard-delete flows, autoscaling, HA, CSV import, mobile apps.
>
> **Numbering note**: this plan was authored as "v2" on 2026-10-27. The slot was renamed to v3 on 2026-10-28 when the Rising Dough redesign was promoted into v2. Multi-user scope folded in on 2026-10-30 (ADR-0061). Scope deltas are additive to Phase 1 (new tasks T-D16..T-D19) and amend the Phase 2 bootstrap outputs; task IDs are unchanged for all prior work.

---

## Contents

- [`implementation_plan.md`](implementation_plan.md) — phased delivery with acceptance gates.
- [`tasks.md`](tasks.md) — flat task index (T-D01…T-D46), referenced from the phase docs.
- [`operator-checklist.md`](operator-checklist.md) — human-only actions (accounts, credentials, real-device checks, operator decisions) that run in parallel with agent work.
- [`phase-1-prerequisites/`](phase-1-prerequisites/) — individual task files for app-side prerequisites.
- [`phase-2-infrastructure/`](phase-2-infrastructure/) — Terraform + cloud-init bootstrap tasks.
- [`phase-3-deployment/`](phase-3-deployment/) — GitHub Actions pipeline tasks.
- [`phase-4-validation/`](phase-4-validation/) — smoke, backup drill, security scan, runbooks.
- [`phase-5-data-protection/`](phase-5-data-protection/) — data-protection quick wins (ADR-0078); full design in [`../v4/`](../v4/README.md).
- [`runbooks/`](runbooks/) — operational procedures created in Phase 4.

---

## At a glance

| Phase | What | Gate |
|---|---|---|
| 1 — Prerequisites | App-side changes (auth, config, SQLite PRAGMAs, Docker, security headers) | Local docker-compose smoke green; new tests at ≥ 90% coverage |
| 2 — Infrastructure | Terraform modules + cloud-init bootstrap; apply to `drill` env | `terraform apply` succeeds; `/health` reachable via public DNS on drill |
| 3 — Deployment | Build + deploy workflows; cosign; rollback script | Push to `main` lands a signed image on `drill`; manual rollback restores previous SHA |
| 4 — Validation | Backup drill; security scan; smoke; monitoring; runbooks | Monthly drill automated; Mozilla Observatory A+; UptimeRobot wired; production acceptance |
| 5 — Data protection | Audit-tail scoping, no-store, age-encrypted replica, 37-day copy ceiling, secure_delete, log hygiene, IP/UA retention, data inventory | ADR-0078 exit criteria; restore drill against encrypted replica |

---

## Dependencies

Phase 2 depends on Phase 1 (needs a `Dockerfile` and a `/health` endpoint before any VM is useful).
Phase 3 depends on Phase 2 (needs the VM and the deploy user before a deploy workflow can run).
Phase 4 depends on Phase 3 (needs real deploys to validate).

Within Phase 1 most tasks are parallel-safe; the data-layer PRAGMA change (T-D05) must land before Litestream config (T-D23 in Phase 2). The multi-user migration (T-D16a) and repository-filter sweep (T-D16) must land before the admin bootstrap service (T-D19) and before any Phase 2 apply (so cloud-init env can inject `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`).

v3 also assumes the v2 redesign has shipped — the deployed artefact is the redesigned app, not the pre-redesign one.

---

## Change policy

Per repo `CLAUDE.md`:

- Any code change in Phase 1 must reference the task id in the commit (`feat(T-Dxx): ...`).
- Any new architectural decision outside the seven ADRs 0032-0037 + 0061 requires a new ADR before code lands.
- Any Terraform resource added outside what ADR-0035 describes requires an amendment to ADR-0035 before `terraform apply`.
- Append a dated line to `docs/CHANGELOG.md` after each merged task.
