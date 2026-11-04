# Phase 5 — Data-protection quick wins (added 2026-11-04)

> Driven by [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md). v3-scope down-payment on the v4 data-protection design ([`docs/plans/v4/`](../../v4/README.md), ADR-0079..0083). No key management, no schema redesign.

| Task | Parallel | Area | Depends on |
|---|---|---|---|
| [T-D54](T-D54-audit-tail-owner-scoped.md) | [P] | app — `/debug/audit-tail` | T-D43 |
| [T-D55](T-D55-no-store-authenticated-responses.md) | [P] | app — middleware | T-D02b, T-D07 |
| [T-D56](T-D56-litestream-age-encryption.md) | [S] | infra — Litestream, cloud-init, runbooks | T-D21, T-D23, T-D41a |
| [T-D57](T-D57-backup-copy-age-ceiling.md) | [S] | infra + app — retention | T-D56, T-D19a |
| [T-D58](T-D58-sqlite-secure-delete.md) | [P] | app — `db/connection.py` | T-D05 |
| [T-D59](T-D59-log-redaction.md) | [P] | app logging + Caddy | T-D06, T-D23 |
| [T-D60](T-D60-ip-user-agent-retention-purge.md) | [P] | app — retention purge | T-D14, T-D19a |
| [T-D61](T-D61-data-inventory-runbook.md) | [S] | docs — runbook | T-D54..T-D60 |

**Gate**: all eight ✅; `just ci` green; frontend-visual-audit not required (no template changes) except T-D55 if it alters logout markup; one restore drill against the age-encrypted replica logged in `runbooks/restore-log.md`.

**Conflict note**: T-D53 (session hardening, ADR-0076) and T-D50 are in flight and both claim ADR-0076 — renumber one before merge. Phase 5 touches `web/middleware/` (T-D55) — coordinate with T-D53 on middleware order (ADR-0070 §6).
