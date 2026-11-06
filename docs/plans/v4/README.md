# v4 — Data Protection Work Plan

> **v4 scope**: keep the v3 functional surface and deployment, and make each user's data **cryptographically** unreadable to anyone not logged in as that user. That includes the admin, the operator at rest, backup holders, and anyone with infrastructure credentials. v4 also adds the **right to be forgotten** and **data portability**. Requirements: [`docs/requirements.md` §7](../../requirements.md#7-v4--data-protection-scope-added-2026-11-04).
>
> **Approach** (decided in [ADR-0079](../../adr/0079-v4-threat-model-and-data-protection-goals.md)): per-user envelope encryption. User-held credentials wrap the keys: password (Argon2id + pepper), PRF passkeys and a recovery code. Fields are encrypted with AES-256-GCM. The server unwraps a user's key only during that user's session, and the session key lives only in their cookie.
>
> **Non-goals**:
> - Client-side end-to-end encryption (v5 candidate).
> - Defeating an operator who actively modifies the running app during sessions (disclosed residual risk).
> - Encrypting structural metadata.
> - Admin or email recovery.
> - Bundle import (v4.1 candidate).

---

## Decisions

| ADR | Topic |
|---|---|
| [0078](../../adr/0078-v3-data-protection-quick-wins.md) | v3 quick wins (prerequisite, `docs/plans/v3/phase-5-data-protection/`) |
| [0079](../../adr/0079-v4-threat-model-and-data-protection-goals.md) | Threat model, hard requirements R1–R4, options evaluated, residual risks |
| [0080](../../adr/0080-v4-envelope-encryption-key-hierarchy-and-sessions.md) | Primitives, key hierarchy (credential → KEK → UMK → DEK), server secrets, session binding, rotation, hygiene |
| [0081](../../adr/0081-v4-field-level-encryption-scope-and-query-model.md) | Encrypted vs plaintext columns, query model, performance budget, expand/contract, feature-preservation matrix |
| [0082](../../adr/0082-v4-account-lifecycle-recovery-and-migration.md) | Key states, escrow → claim migration, new users, passkeys/PRF, recovery code, admin reset semantics |
| [0083](../../adr/0083-v4-right-to-be-forgotten-portability-and-retention.md) | Deactivate vs erase, erasure procedure, erasure ledger, export bundle, keyless operations, retention schedule, `/privacy` |

## Contents

- [`implementation_plan.md`](implementation_plan.md): phases, entry and exit gates, rollout order, guardrails.
- [`tasks.md`](tasks.md): task index T-E01…T-E26, with full deliverables, acceptance criteria and validation hooks per task.
- [`operator-checklist.md`](operator-checklist.md): human-only steps (secrets, user communication, rollout approvals).

## At a glance

| Phase | What | Gate |
|---|---|---|
| 0 — Preconditions | v3 Phase 5 (T-D54..T-D61) and T-D53 session hardening merged; ADR-0079..0083 Accepted; post-v3 quality audit complete (`docs/plans/quality-audit/`) | operator sign-off |
| 1 — Crypto core and secrets | `budget_planner.crypto`, server secrets, key-wrap schema | property tests green; prod refuses to start without secrets |
| 2 — Session binding and unlock | keys from login, cookie-held SWK, locked sessions, PRF passkeys, claim + recovery code | auth e2e green; frontend audit |
| 3 — Field encryption | expand migration, repository sweep, aggregates in Python, static check, backfill, perf budget | full suite green unchanged; ≤ +50 ms p95; byte-scan clean |
| 4 — Lifecycle and Security tab | password change, admin reset → recover, Data protection section, key hygiene | lifecycle e2e green; frontend audit |
| 5 — Erasure, export, retention | erasure service, ledger + replay, export bundle, demo builder, `/privacy` | erasure e2e + restore-replay drill green |
| 6 — Rollout and contract | smoke + canary, prod v4.0 rollout, contract migration, security review | no `plaintext` users; contract released; scans clean |
