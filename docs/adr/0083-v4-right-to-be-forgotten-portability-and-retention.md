# ADR-0083: v4 Right to Be Forgotten, Data Portability, Retention Schedule, Keyless Operations

- **Status**: Proposed
- **Date**: 2026-11-04
- **Amends**:
  - [ADR-0019](0019-soft-delete-and-audit-log.md) (hard purge on erasure overrides soft delete; audit rows pseudonymized)
  - [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) ("Remove user" = deactivate; new "Erase")
  - [ADR-0073](0073-user-admin-panel-guard-and-one-shot-password.md) (admin panel actions)
  - [ADR-0034](0034-v3-sqlite-replication-litestream.md) (second replicated DB: erasure ledger)
  - [ADR-0078](0078-v3-data-protection-quick-wins.md) §1 (audit tail) and §4 (37-day ceiling is now a user-facing promise)
  - requirements §6.8 (the hard-delete non-goal is lifted)
- **Related**: [ADR-0079](0079-v4-threat-model-and-data-protection-goals.md) R4, [ADR-0080](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md), [ADR-0082](0082-v4-account-lifecycle-recovery-and-migration.md)

## Context

R4 asks for the right to be forgotten. v3 can only soft-delete a user (ADR-0061), so all their rows stay, along with their audit history, IP addresses and backups. The legal frame is GDPR Article 17 (erasure), Article 20 (portability) and Article 5(1)(e) (storage limitation). The operator acts as the controller.

This ADR makes erasure technically real and bounded in time. It also covers the operations that ran against user data without that user present, since encryption (ADR-0080) breaks them. It's an engineering record, not legal advice. The user-facing wording on `/privacy` should be reviewed by the operator.

## Decision

### 1. Two different removals

| Action | Who | Effect | Reversible |
|---|---|---|---|
| **Deactivate** (v3 "Remove", renamed) | admin | soft-delete `users` row, revoke sessions; data kept (ciphertext) | yes, until auto-erasure |
| **Erase** | the user (self-service), an admin, or the retention job | §3 procedure | **no** |

Deactivated users are **auto-erased after 90 days** unless reactivated (storage limitation). The admin panel shows the countdown. Erasure needs no keys, so the job runs unattended (§6).

### 2. Triggers and guards

- **Self-service**: Settings → Security → Data protection → "Delete my account and data".
  - Requires step-up re-auth (ADR-0076) and typing the account email.
  - The screen offers the export (§5) first.
  - The last-admin invariant (ADR-0061) applies: the last admin must promote someone else first.
- **Admin**: `/settings/users` → "Erase user…".
  - Requires step-up re-auth, typing the target's email, and a confirmation dialog that states irreversibility.
  - An admin can't erase themselves from the admin panel; they use the self-service path.
- **Retention job**: deactivated more than 90 days.

### 3. Erasure procedure (`services/erasure.py`, one SQLite transaction)

1. **Revoke and delete every session** of the user. This destroys the session-wrapped keys (ADR-0080 §4).
2. **Crypto-shred**: hard-delete every `user_key_wraps` row of the user. From this point no ciphertext of this user in the live DB can be decrypted by anyone.
3. **Hard-delete all user-owned rows**:
   - `transactions`, `planned_transactions`, `recurring_rules`, `recurring_rule_overrides`, `account_snapshots`, `accounts`, `categories`;
   - `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences`;
   - `webauthn_credentials`;
   - `auth_rate_limit` rows keyed on the user's id or email.
   - The deletion order respects foreign keys. `secure_delete` (ADR-0078 §6) zeroes the freed pages.
4. **Audit log**:
   - Rows for the user's own entities are **deleted**. Their payloads were ciphertext under the shredded key anyway.
   - Auth and admin events where the user is the subject or the actor are **pseudonymized**: `ip`, `user_agent` and `session_id` are set to `NULL`, and any `email` / `name` inside a payload is replaced with `"[erased]"`. The integer `user_id` stays as a pseudonymous reference, which keeps the audit chain and the admin's own history consistent.
   - One new row records the erasure: `entity_type='user'`, `operation='erase'`, `new_json={"erased_at": …, "by": "self"|"admin"|"retention"}`. No email.
5. **Tombstone the `users` row**: `email`, `name` and `password_hash` set to `NULL`, `key_state='erased'`, `erased_at` set. The row stays so integer references remain valid and the id is never reused.
6. **Erasure ledger**: append `(user_id, erased_at)` to the erasure ledger (§4).
7. **Receipt**. Self-service users see a final confirmation page, and admins see a panel toast, with the erasure timestamp and the statement: *"Backup copies expire by <erased_at + 37 days>. Until then they remain encrypted with keys that no longer exist on the live system."*

The procedure is idempotent. Re-running it on an `erased` user is a no-op that returns the original receipt.

### 4. Backups and the erasure ledger

- Backups are bounded at **37 days** (ADR-0078 §4). After erasure, backups within that window still contain the user's ciphertext and wrapped keys. Opening them still requires the user's own credentials, which the user has abandoned, and the copies expire on schedule. That's the "beyond use" treatment backups commonly get under GDPR. It's stated on `/privacy`.
- **No resurrection after a restore.** Restoring an older backup could bring an erased user back. To prevent that, the app keeps an **erasure ledger**: a separate SQLite file, `/data/erasure_ledger.db`, holding only `(user_id, erased_at)`, no personal data. It's replicated by Litestream as a second DB with **unbounded** retention (it's tiny, append-only and pseudonymous), and age-encrypted like the main replica.
- After any restore, the restore scripts (`litestream-restore` entrypoint step, `restore-from-prod`, `runbooks/restore.md`) run `python -m budget_planner.cli.replay_erasures`. It re-applies §3 for every ledger entry newer than the restored DB's state. The app refuses to start in production while ledger entries are unapplied (readiness check, `/ready` returns 503).

### 5. Portability (export)

- Settings → Security → Data protection → **"Export all my data"** produces a schema-versioned JSON bundle (`budget-planner-export/v1`). It contains every user-owned entity decrypted, the preferences, and the user's own audit history.
- The existing per-surface CSV and Parquet exports stay.
- Exports are audited (`auth_event: export`) and rate-limited (scope `export`, 5/h per user). They aren't step-up guarded, consistent with ADR-0076's reasoning: a hijacked session can read every page anyway.
- Import of a bundle into a new account is **out of v4 scope** (v4.1 candidate). The format is designed so import is possible: stable ids within the bundle, explicit currencies, no derived values.

### 6. Operations that ran without the user present

| Operation | v3 | v4 |
|---|---|---|
| `data/scripts/build_demo_db.py` | copies prod DB, anonymizes | **Reads an export bundle** (`--from-export <bundle.json>`) that the operator downloads from their own account. The `budget.sqlite` basename tripwire is replaced by a bundle-schema check, and the script refuses a bundle whose `exported_by` isn't the operator's own account email. It no longer opens the prod DB at all. |
| Restore drill (T-D40/T-D41) | `integrity_check` + audit tail | plus a **decrypt canary**. A dedicated `canary@` user in prod holds synthetic data only. Its credentials are a GitHub environment secret. After restore the drill signs in as the canary and asserts a known transaction decrypts, which proves the keys and the pepper survived the restore. |
| T-D43 smoke journey | sees audit payloads | adds the claim and recovery-code steps (ADR-0082); audit tail asserts metadata only for the other user |
| `/debug/audit-tail` | owner-scoped payloads (ADR-0078 §1) | own payloads decrypted with the caller's keys; others' stay ciphertext and are shown as `"[other-user]"` |
| Retention purge (ADR-0078 §7), deactivation auto-erasure | n/a | keyless; unchanged |
| FX refresh | global | unchanged |
| Startup migrations | schema + data | schema-only at boot; value transforms are per-user lazy (ADR-0081 §5) |
| Operator `set_password` CLI | resets password | resets **sign-in only** (ADR-0082 §5) |

### 7. Retention schedule

| Data | Retained until |
|---|---|
| Live user data | erasure (self, admin, or 90 days after deactivation) |
| Sessions | deleted 90 days after expiry or revocation (ADR-0078 §7); deleted at erasure |
| IP / user agent in audit and sessions | 90 days (ADR-0078 §7); nulled at erasure |
| Audit rows for user entities | erasure (deleted) |
| Auth/admin audit events | indefinitely, pseudonymized at erasure |
| App and Caddy logs | 14 days (ADR-0078 §5) |
| Backups (all copies) | 37 days (ADR-0078 §4) |
| Erasure ledger | indefinitely (ids + timestamps only) |

### 8. `/privacy` — "What the operator can and cannot see"

- A public page: it's static, exempt from auth like `/health`, and linked from the login page and from Security → Data protection.
- It states, in plain language:
  - what is encrypted and what metadata isn't (ADR-0081 §4);
  - the residual risks (ADR-0079);
  - that lost credentials can't be recovered (ADR-0082);
  - the retention schedule (§7);
  - how to export and erase.
- The source of truth is this ADR set. A doc-sync test fails if the retention values on the page and in `config.py` diverge.

## Consequences

- Erasure is immediate and cryptographic on the live system, and bounded at 37 days across all copies. Restores can't resurrect erased users.
- Soft delete (ADR-0019) remains the normal edit and undo model. Erasure is the single, explicit hard-delete path, guarded and audited.
- The demo DB pipeline changes from "copy prod" to "export my own data", a real improvement: it no longer opens the prod DB.
- One more replicated file (the erasure ledger) and one more drill assertion (the decrypt canary).
