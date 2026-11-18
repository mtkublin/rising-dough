# T-D56 — Litestream replica encryption (age) + version alignment

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: no
- **Depends on**: T-D21, T-D23, T-D41a
- **Blocks**: T-D57
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §3, [ADR-0112](../../../adr/0112-prod-gated-litestream-plaintext-cleanup.md), [ADR-0034](../../../adr/0034-v3-sqlite-replication-litestream.md)

## Context

The replica relies on provider SSE only: anyone with the bucket credential restores the full DB in plaintext. Prod pins `litestream/litestream:0.3`; prod-sim uses `0.5.0` (replicate) and `0.5.17` (restore) — unintended skew.

## Deliverables

1. **Version decision** (recorded in the handoff): check release notes of the latest 0.3.x and 0.5.x for replica `age` support. Pin **one exact tag** (no floating `0.3`) in `docker-compose.yml` (both services) and `terraform/cloud-init/compose/docker-compose.yml.tpl` (both services). If 0.5.x lacks age, pin latest 0.3.x everywhere.
2. Replica config — `deploy/litestream.yml` and `terraform/cloud-init/compose/litestream.yml.tpl`: `age: { recipients: [<pub>] }` on replicate; restore configs add `identities: [<file>]`.
3. Terraform: sensitive variable `litestream_age_identity` (+ derived public recipient) → cloud-init writes `/etc/budget-planner/litestream-age.key` at `0600` (pattern of ADR-0069 secrets). Prod-sim uses a committed **dev-only** identity under `deploy/` flagged in `.secrets.baseline` with an allowlist comment — never reused for drill/prod.
4. `terraform/cloud-init/bin/restore-from-prod.tpl`, `runbooks/restore.md`, `runbooks/disaster-recovery.md`: identity path + "lost identity = unrecoverable replica" warning.
5. Cut-over runbook section: new generation with encryption → restore drill → delete unencrypted generations (`litestream` CLI or bucket prefix delete) → noncurrent versions expire per T-D57.
6. Operator checklist item (generate with `age-keygen`, store in password manager).

## Acceptance criteria

- Prod-sim: `just test-prod-stack` replicates to MinIO; raw objects in the bucket are age ciphertext (each object starts with the `age-encryption.org/v1` header; LZ4-decompressing them fails); `litestream restore` with the identity yields a DB passing `PRAGMA integrity_check`.
- Restore **without** the identity fails.
- Drill env restore drill (T-D41 workflow) green against the encrypted replica; entry in `runbooks/restore-log.md`.

## Validation hook

```sh
just test-prod-stack
gh workflow run restore-drill.yml   # drill env
```

## Status (2026-11-18): code done, cut-over pending (◐)

- **Done**: version pin 0.3.14, replica config, identity path, restore helper, runbook, and the prod-gated cleanup workflow `litestream-plaintext-cleanup.yml` + `scripts/ci/litestream_cleanup.py` (ADR-0112). Cut-over steps: [`restore.md`](../runbooks/restore.md#cut-over-to-an-encrypted-replica-t-d56-adr-0078-3-adr-0112).
- **Prod state (from code, not observed)**: prod Litestream has run the age config since the v3.0.1 release through the host agent (2026-11-18). Litestream 0.3.14 does **not** open a new generation when age is enabled (`replica.go`): the current generation continues, new snapshots and WAL segments are ciphertext, older objects stay plaintext. So the bucket most likely holds a mixed generation plus older plaintext generations. Unconfirmed until someone lists the bucket (the cleanup dry run does exactly that).
- **Restart risk fixed by T-D136 (ADR-0114)**: the replicate config now has `age.identities` and the litestream entrypoint forces one new generation per host. **The cut-over depends on T-D136 being live on prod and verified on a drill (DRILL-2).** Until then a Litestream restart stalls replication.
- **Local prod-sim acceptance**: not run (Docker daemon not available to the agent). Still to do on a machine with Docker: `just test-prod-stack`, objects start with the age header, restore with identity passes `integrity_check`, restore without it fails.
- **Remaining**: restore drill green against the encrypted replica (T-D40), then cleanup dry run, review, apply (needs the operator's approval click).
